"""Dobot TCP 会话封装：连接、使能、运动、读位姿、停止。"""
import re
import socket
import threading
import time
from time import sleep

from DobotDemo import DobotDemo


def parse_numbers(value_recv: str) -> list[int]:
    if "Not Tcp" in value_recv:
        raise RuntimeError("机械臂未处于 TCP 控制模式，请先在示教器切换到 TCP/IP 远程控制")
    nums = [int(n) for n in re.findall(r"-?\d+", value_recv)]
    if not nums:
        raise RuntimeError(f"无法解析控制器返回: {value_recv}")
    return nums


def parse_pose(value_recv: str) -> list[float]:
    if "Not Tcp" in value_recv:
        raise RuntimeError("机械臂未处于 TCP 控制模式，请先在示教器切换到 TCP/IP 远程控制")
    nums = re.findall(r"-?\d+\.?\d*", value_recv)
    # GetPose 返回格式通常为: 0,{x,y,z,rx,ry,rz}，首项是状态码而非坐标
    if len(nums) >= 7:
        status = int(float(nums[0]))
        if status != 0:
            raise RuntimeError(f"读取位姿失败: {value_recv}")
        return [float(x) for x in nums[1:7]]
    if len(nums) < 6:
        raise RuntimeError(f"无法解析位姿: {value_recv}")
    return [float(x) for x in nums[:6]]


class RobotSession(DobotDemo):
    """基于 DobotDemo.py 的连接/反馈逻辑，对外提供稳定运动 API。"""

    def __init__(self, ip):
        super().__init__(ip)
        self.feedFour = None
        self._feed_running = False
        self._enabled = False

    def _ensure_socket_connected(self, api, port: int, label: str) -> None:
        if api is None or getattr(api, "socket_dobot", 0) == 0:
            raise RuntimeError(
                f"连接机械臂 {self.ip}:{port} 失败（{label}），"
                "请检查 IP、网络、示教器 TCP/IP 远程控制和端口占用"
            )

    def connect(self) -> None:
        from dobot_api import DobotApiDashboard, DobotApiFeedBack

        if self.dashboard is not None:
            return

        self.dashboard = DobotApiDashboard(self.ip, self.dashboardPort)
        self._ensure_socket_connected(self.dashboard, self.dashboardPort, "控制端口")

        # 连通性检查：发一条测试指令，5 秒无响应则报错
        sock = getattr(self.dashboard, "socket_dobot", 0)
        if sock and sock != 0:
            try:
                sock.settimeout(5)
                sock.send(b"GetPose()\r\n")
                test_data = sock.recv(1024)
                sock.settimeout(None)  # 恢复阻塞模式，后续 wait_reply 正常运作
                if not test_data or len(test_data) == 0:
                    raise RuntimeError("机械臂无响应")
            except (OSError, socket.timeout):
                self.disconnect()
                raise RuntimeError(
                    f"连接机械臂 {self.ip}:{self.dashboardPort} 失败，"
                    "请检查：\n"
                    "1. 机械臂 IP 是否正确\n"
                    "2. 网络是否可达\n"
                    "3. 示教器是否已切换到 TCP/IP 远程控制\n"
                    "4. 示教器 29999/30004 端口是否被其他软件占用"
                ) from None

        try:
            self.feedFour = DobotApiFeedBack(self.ip, self.feedPortFour)
            self._ensure_socket_connected(self.feedFour, self.feedPortFour, "反馈端口")
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
            raise RuntimeError("使能失败，请检查 29999 端口是否被占用")
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
            raise RuntimeError(f"设置速度失败: {result}")

    def get_pose(self) -> list[float]:
        return parse_pose(self.dashboard.GetPose())

    def get_robot_mode(self) -> int:
        """返回机器人模式：5=已使能就绪, 9=报警。从反馈线程数据读取。"""
        try:
            return self.feedData.robotMode
        except Exception:
            return -1

    def clear_alarm(self) -> None:
        """清除控制器报警状态。"""
        result = parse_numbers(self.dashboard.ClearError())
        if result[0] != 0:
            raise RuntimeError(f"清除报警失败: {result}")

    def get_joints(self) -> list[float]:
        """读取当前关节角度 [J1,J2,J3,J4,J5,J6]"""
        return parse_pose(self.dashboard.GetAngle())

    def _wait_command(self, recv: str, timeout: float = 15.0) -> None:
        parsed = parse_numbers(recv)
        if parsed[0] != 0:
            raise RuntimeError(f"运动指令失败: {recv}")
        cmd_id = parsed[1]
        deadline = time.monotonic() + timeout
        while True:
            if self.feedData.robotMode == 5 and self.feedData.robotCurrentCommandID == cmd_id:
                break
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "机械臂运动执行超时，请检查：\n"
                    "1. 机械臂是否已使能\n"
                    "2. 机械臂是否处于急停状态\n"
                    "3. 机械臂是否已断开连接"
                )
            sleep(0.1)

    def _run_move(self, move_fn, point: list[float], coordinate_mode: int = 0, v: int = 50) -> None:
        if len(point) != 6:
            raise ValueError("位姿/关节必须为 6 个数")
        kwargs = {}
        if v > 0:
            kwargs["v"] = v
        recv = move_fn(*point, coordinate_mode, **kwargs)
        self._wait_command(recv)

    def movj(self, point: list[float], v: int = 50) -> None:
        self._run_move(self.dashboard.MovJ, point, 0, v)

    def movj_joint(self, joint: list[float], v: int = 50) -> None:
        """关节模式运动：joint=[J1,J2,J3,J4,J5,J6]"""
        self._run_move(self.dashboard.MovJ, joint, 1, v)

    def movl(self, point: list[float], v: int = 50) -> None:
        self._run_move(self.dashboard.MovL, point, 0, v)

    def arc(self, through_point: list[float], end_point: list[float], v: int = 50) -> None:
        if len(through_point) != 6 or len(end_point) != 6:
            raise ValueError("圆弧中间点/目标点必须为 6 个数")
        kwargs = {}
        if v > 0:
            kwargs["v"] = v
        recv = self.dashboard.Arc(*through_point, *end_point, 0, **kwargs)
        self._wait_command(recv)

    def circle(self, through_point: list[float], end_point: list[float], count: int = 1, v: int = 50) -> None:
        if len(through_point) != 6 or len(end_point) != 6:
            raise ValueError("整圆中间点/结束点必须为 6 个数")
        kwargs = {}
        if v > 0:
            kwargs["v"] = v
        recv = self.dashboard.Circle(*through_point, *end_point, 0, int(count), **kwargs)
        self._wait_command(recv)

    def disconnect(self) -> None:
        """关闭 TCP 连接，避免交互模式下端口被占用。"""
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
