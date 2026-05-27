"""Dobot TCP 会话封装：连接、使能、运动、读位姿、停止。"""
import re
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
        self._feed_running = False
        self._enabled = False

    def connect(self) -> None:
        from dobot_api import DobotApiDashboard, DobotApiFeedBack

        if self.dashboard is not None:
            return

        self.dashboard = DobotApiDashboard(self.ip, self.dashboardPort)
        self.feedFour = DobotApiFeedBack(self.ip, self.feedPortFour)
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

    def _wait_command(self, recv: str) -> None:
        parsed = parse_numbers(recv)
        if parsed[0] != 0:
            raise RuntimeError(f"运动指令失败: {recv}")
        cmd_id = parsed[1]
        deadline = time.monotonic() + 120
        while True:
            if self.feedData.robotMode == 5 and self.feedData.robotCurrentCommandID == cmd_id:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("等待运动完成超时，请检查反馈线程或关闭其他占用端口的软件")
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

        if self.feedFour is not None:
            feed = self.feedFour
            self.feedFour = None
            try:
                feed.close()
            except Exception:
                pass
