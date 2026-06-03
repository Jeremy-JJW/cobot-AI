"""Dobot TCP 會話封裝：連接、使能、運動、讀位姿、停止。"""
import re
import socket
import threading
import time
from time import sleep

from DobotDemo import DobotDemo


def parse_numbers(value_recv: str) -> list[int]:
    if "Not Tcp" in value_recv:
        raise RuntimeError("機械臂未處於 TCP 控制模式，請先在示教器切換到 TCP/IP 遠程控制")
    nums = [int(n) for n in re.findall(r"-?\d+", value_recv)]
    if not nums:
        raise RuntimeError(f"無法解析控制器返回: {value_recv}")
    return nums


def parse_pose(value_recv: str) -> list[float]:
    if "Not Tcp" in value_recv:
        raise RuntimeError("機械臂未處於 TCP 控制模式，請先在示教器切換到 TCP/IP 遠程控制")
    nums = re.findall(r"-?\d+\.?\d*", value_recv)
    # GetPose 返回格式通常爲: 0,{x,y,z,rx,ry,rz}，首項是狀態碼而非座標
    if len(nums) >= 7:
        status = int(float(nums[0]))
        if status != 0:
            raise RuntimeError(f"讀取位姿失敗: {value_recv}")
        return [float(x) for x in nums[1:7]]
    if len(nums) < 6:
        raise RuntimeError(f"無法解析位姿: {value_recv}")
    return [float(x) for x in nums[:6]]


class RobotSession(DobotDemo):
    """基於 DobotDemo.py 的連接/反饋邏輯，對外提供穩定運動 API。"""

    def __init__(self, ip):
        super().__init__(ip)
        self.feedFour = None
        self._feed_running = False
        self._enabled = False

    def _ensure_socket_connected(self, api, port: int, label: str) -> None:
        if api is None or getattr(api, "socket_dobot", 0) == 0:
            raise RuntimeError(
                f"連接機械臂 {self.ip}:{port} 失敗（{label}），"
                "請檢查 IP、網絡、示教器 TCP/IP 遠程控制和端口占用"
            )

    def connect(self) -> None:
        from dobot_api import DobotApiDashboard, DobotApiFeedBack

        if self.dashboard is not None:
            return

        self.dashboard = DobotApiDashboard(self.ip, self.dashboardPort)
        self._ensure_socket_connected(self.dashboard, self.dashboardPort, "控制端口")

        # 連通性檢查：發一條測試指令，5 秒無響應則報錯
        sock = getattr(self.dashboard, "socket_dobot", 0)
        if sock and sock != 0:
            try:
                sock.settimeout(5)
                sock.send(b"GetPose()\r\n")
                test_data = sock.recv(1024)
                sock.settimeout(None)  # 恢復阻塞模式，後續 wait_reply 正常運作
                if not test_data or len(test_data) == 0:
                    raise RuntimeError("機械臂無響應")
            except (OSError, socket.timeout):
                self.disconnect()
                raise RuntimeError(
                    f"連接機械臂 {self.ip}:{self.dashboardPort} 失敗，"
                    "請檢查：\n"
                    "1. 機械臂 IP 是否正確\n"
                    "2. 網絡是否可達\n"
                    "3. 示教器是否已切換到 TCP/IP 遠程控制\n"
                    "4. 示教器 29999/30004 端口是否被其他軟件佔用"
                ) from None

        try:
            self.feedFour = DobotApiFeedBack(self.ip, self.feedPortFour)
            self._ensure_socket_connected(self.feedFour, self.feedPortFour, "反饋端口")
        except Exception:
            self.disconnect()
            raise

        self._feed_running = True
        feed_thread = threading.Thread(target=self.GetFeed, daemon=True)
        feed_thread.start()
        sleep(0.3)

    def GetFeed(self):
        while self._feed_running:
            try:
                if self.feedFour is None:
                    break
                feedInfo = self.feedFour.feedBackData()
            except OSError:
                break
            except Exception:
                sleep(0.1)
                continue

            with self._DobotDemo__globalLockValue:
                if feedInfo is not None:
                    if hex((feedInfo["TestValue"][0])) == "0x123456789abcdef":
                        self.feedData.MessageSize = feedInfo["len"][0]
                        self.feedData.robotMode = feedInfo["RobotMode"][0]
                        self.feedData.DigitalInputs = feedInfo["DigitalInputs"][0]
                        self.feedData.DigitalOutputs = feedInfo["DigitalOutputs"][0]
                        self.feedData.robotCurrentCommandID = feedInfo["CurrentCommandId"][0]

    def enable(self) -> None:
        if self._enabled:
            return
        result = parse_numbers(self.dashboard.EnableRobot())
        if result[0] != 0:
            raise RuntimeError("使能失敗，請檢查 29999 端口是否被佔用")
        self._enabled = True

    def disable(self) -> None:
        if self.dashboard is None or not self._enabled:
            return
        self.dashboard.DisableRobot()
        self._enabled = False

    def stop(self) -> None:
        self.dashboard.Stop()

    def set_speed(self, percent: int) -> None:
        result = parse_numbers(self.dashboard.SpeedFactor(int(percent)))
        if result[0] != 0:
            raise RuntimeError(f"設置速度失敗: {result}")

    def get_pose(self) -> list[float]:
        return parse_pose(self.dashboard.GetPose())

    def get_robot_mode(self) -> int:
        """返回機器人模式：5=已使能就緒, 9=報警。從反饋線程數據讀取。"""
        try:
            return self.feedData.robotMode
        except Exception:
            return -1

    def clear_alarm(self) -> None:
        """清除控制器報警狀態。"""
        result = parse_numbers(self.dashboard.ClearError())
        if result[0] != 0:
            raise RuntimeError(f"清除報警失敗: {result}")

    def get_joints(self) -> list[float]:
        """讀取當前關節角度 [J1,J2,J3,J4,J5,J6]"""
        return parse_pose(self.dashboard.GetAngle())

    def _wait_command(self, recv: str, timeout: float = 15.0) -> None:
        parsed = parse_numbers(recv)
        if parsed[0] != 0:
            raise RuntimeError(f"運動指令失敗: {recv}")
        cmd_id = parsed[1]
        deadline = time.monotonic() + timeout
        while True:
            if self.feedData.robotMode == 5 and self.feedData.robotCurrentCommandID == cmd_id:
                break
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "機械臂運動執行超時，請檢查：\n"
                    "1. 機械臂是否已使能\n"
                    "2. 機械臂是否處於急停狀態\n"
                    "3. 機械臂是否已斷開連接"
                )
            sleep(0.1)

    def _run_move(self, move_fn, point: list[float], coordinate_mode: int = 0, v: int = 50) -> None:
        if len(point) != 6:
            raise ValueError("位姿/關節必須爲 6 個數")
        kwargs = {}
        if v > 0:
            kwargs["v"] = v
        recv = move_fn(*point, coordinate_mode, **kwargs)
        self._wait_command(recv)

    def movj(self, point: list[float], v: int = 50) -> None:
        self._run_move(self.dashboard.MovJ, point, 0, v)

    def movj_joint(self, joint: list[float], v: int = 50) -> None:
        """關節模式運動：joint=[J1,J2,J3,J4,J5,J6]"""
        self._run_move(self.dashboard.MovJ, joint, 1, v)

    def movl(self, point: list[float], v: int = 50) -> None:
        self._run_move(self.dashboard.MovL, point, 0, v)

    def arc(self, through_point: list[float], end_point: list[float], v: int = 50) -> None:
        if len(through_point) != 6 or len(end_point) != 6:
            raise ValueError("圓弧中間點/目標點必須爲 6 個數")
        kwargs = {}
        if v > 0:
            kwargs["v"] = v
        recv = self.dashboard.Arc(*through_point, *end_point, 0, **kwargs)
        self._wait_command(recv)

    def circle(self, through_point: list[float], end_point: list[float], count: int = 1, v: int = 50) -> None:
        if len(through_point) != 6 or len(end_point) != 6:
            raise ValueError("整圓中間點/結束點必須爲 6 個數")
        kwargs = {}
        if v > 0:
            kwargs["v"] = v
        recv = self.dashboard.Circle(*through_point, *end_point, 0, int(count), **kwargs)
        self._wait_command(recv)

    def disconnect(self) -> None:
        """關閉 TCP 連接，避免交互模式下端口被佔用。"""
        self._feed_running = False
        sleep(0.2)

        if self.dashboard is not None:
            dashboard = self.dashboard
            self.dashboard = None
            try:
                dashboard.close()
            except Exception:
                pass

        if getattr(self, "feedFour", None) is not None:
            feed = self.feedFour
            self.feedFour = None
            try:
                feed.close()
            except Exception:
                pass
