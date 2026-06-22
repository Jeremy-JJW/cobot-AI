# 越疆协作臂 Lua5 可用指令白名单与映射表

> 来源：`1.cobot用户手册（脚本编程部分.md`（附录C 脚本编程函数说明）。
> 用途：`lua_exporter.py` 据此把程序 IR 翻译成 `.lua`。仅使用本表中确认可用的指令。

## 一、点位定义

```lua
P1 = {pose = {x, y, z, rx, ry, rz}}   -- 笛卡尔点（本项目统一用 pose）
```

## 二、运动指令

| Lua 指令 | 说明 | 关键可选参数 |
|----------|------|--------------|
| `MovJ(P1, {opt})` | 关节运动到点 | `v`(速度%)、`a`(加速度%)、`cp`(平滑过渡比例)、`stopcond` |
| `MovL(P1, {opt})` | 直线运动到点 | `v`、`a`、`speed`(绝对mm/s)、`cp`、`r`(平滑过渡半径)、`stopcond` |
| `Arc(P1, P2, {opt})` | 经 P1 圆弧到 P2 | 同上 |
| `Circle(P1, P2, Count, {opt})` | 整圆 Count 圈 | 同上 |
| `MovJIO/MovLIO(P, {{Mode,Distance,Index,Status}}, {opt})` | 运动途中触发 DO | — |

示例：

```lua
MovJ(P1, {v = 30})
MovL(P2, {v = 30, cp = 50})   -- 50% 平滑过渡，连续轨迹更顺
MovL(P3, {v = 30, r = 5})     -- 5mm 过渡半径
```

## 三、运动参数

| Lua 指令 | 说明 |
|----------|------|
| `SpeedFactor(ratio)` | 设置全局运动速率（百分比，如 `SpeedFactor(50)`） |

## 四、IO

| Lua 指令 | 说明 |
|----------|------|
| `DO(index, ON\|OFF, time_ms)` | 设置数字输出，`time_ms` 可选（到时自动取反），如 `DO(1, ON)` / `DO(1, ON, 50)` |
| `DI(index)` | 读取数字输入状态（ON/OFF），用于条件表达式 |
| `GetDO(index)` | 读取数字输出状态 |
| `ToolDO(index, ON\|OFF)` | 设置末端数字输出 |
| `ToolDI(index)` | 读取末端数字输入 |

## 五、程序控制 / 等待

| Lua 指令 | 说明 |
|----------|------|
| `Wait(time_ms)` | 等待固定毫秒，如 `Wait(300)` |
| `Wait(check_str)` | 等待条件成立，如 `Wait("DI(1) == ON")` |
| `Wait(check_str, timeout_ms)` | 带超时等待条件 |
| `Sleep(time_ms)` | 休眠（与 Wait(ms) 等价用法，本项目统一用 Wait(ms)） |
| `print(str)` | 控制台打印 |

## 六、条件执行（DI 触发）

Lua 中条件判断使用标准 `if ... then ... end`，配合 `DI(index) == ON`：

```lua
if DI(2) == ON then
  MovL(P1, {v = 30})
end
```

---

## 七、本项目 IR → Lua 映射

| IR skill | params | 生成的 Lua |
|----------|--------|-----------|
| `set_speed` | `speed_percent` | `SpeedFactor(<speed_percent>)` |
| `move_to_program_point` | `point`, `move_type`, `speed_percent` | `MovJ(<point>, {v=<speed>})` 或 `MovL(<point>, {v=<speed>, cp=<cp>})` |
| `set_do` | `index`, `state` | `DO(<index>, ON\|OFF)` |
| `wait_di` | `index`, `state`, `timeout_seconds` | `Wait("DI(<index>) == ON\|OFF", <timeout_ms>)` |
| `wait` | `seconds` | `Wait(<seconds*1000>)` |
| `move_relative_linear`（兜底） | `axis`, `direction`, `distance_mm` | `RelMovL` / 注释提示 |

带 `condition = {di, state}` 的任意指令：外层包裹

```lua
if DI(<di>) == <ON|OFF> then
  <指令>
end
```

> 说明：`ON`/`OFF` 在越疆 Lua 中为内建常量，直接书写不加引号。
