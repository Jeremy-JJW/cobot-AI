# Skill 与话术（OpenClaw 知识库用）

> 本文件给 OpenClaw **知识库**使用。系统行为以 `openclaw_system_prompt.txt` 为准。  
> **最后同步**：2026-05-27（与 `skill_registry.json`、`robot_planner_prompt.txt` 一致）  
> **配置入口**：完整喂文件清单见 `openclaw_首次任务.txt` 第一节

## 项目路径

```
Z:\Cursor_contents\cobot+AI应用
```

Python 代码已在该目录，**不要**在对话里重新生成控制程序。

---

## Skill 白名单（共 10 个）

| # | Skill | 说明 |
|---|-------|------|
| 1 | move_relative_linear | 单步 X/Y/Z 相对直线 |
| 2 | move_relative_sequence | 一条指令 2～10 步相对直线 |
| 3 | move_to_named_point | 去命名点 |
| 4 | move_between_points | 两点间运动 |
| 5 | motion_pattern | 20 种预置复合轨迹 |
| 6 | set_speed | 全局速度 |
| 7 | wait | 等待 |
| 8 | read_pose | 读位姿 / 标定点 |
| 9 | stop_or_disable | 停止 / 下使能 |
| 10 | enable_robot | 上使能 |

---

### 1. move_relative_linear — 相对直线移动

| 参数 | 类型 | 说明 |
|------|------|------|
| axis | x / y / z | 轴 |
| direction | + / - | 方向 |
| distance_mm | 0.1～200 | 距离毫米 |
| speed_percent | 1～50，默认 30 | 可选 |

**话术示例**

- 向 X 正方向移动 100 毫米
- 向 Z 负方向移动 50mm
- 抬高 100 毫米 → axis=z, direction=+, distance_mm=100
- 下降 50 毫米 → axis=z, direction=-, distance_mm=50

**JSON 示例**

```json
{
  "explain": "沿 Z 正方向直线移动 100 毫米",
  "skill": "move_relative_linear",
  "params": {
    "axis": "z",
    "direction": "+",
    "distance_mm": 100,
    "speed_percent": 30
  }
}
```

---

### 2. move_relative_sequence — 多步相对直线

| 参数 | 类型 | 说明 |
|------|------|------|
| steps | 数组 | 2～10 步，每步含 axis/direction/distance_mm |
| speed_percent | 1～50，默认 30 | 可选 |

**话术示例**

- 先 x+50mm，再 y+50mm
- 先向 X 正方向移动 50 毫米，再向 Y 正方向移动 50 毫米
- 先抬高 10 毫米，然后向 X 正方向移动 20 毫米，接着向 Y 正方向移动 20 毫米
- 第一步向 X 正方向移动 30 毫米，第二步向 Y 正方向移动 30 毫米，第三步抬高 20 毫米

**JSON 示例**

```json
{
  "explain": "先 X+50mm，再 Y+50mm",
  "skill": "move_relative_sequence",
  "params": {
    "steps": [
      {"axis": "x", "direction": "+", "distance_mm": 50},
      {"axis": "y", "direction": "+", "distance_mm": 50}
    ],
    "speed_percent": 30
  }
}
```

---

### 3. move_to_named_point — 移动到命名点

| 参数 | 说明 |
|------|------|
| point | home / point_a / point_b |
| move_type | movj（默认）或 movl |
| speed_percent | 可选，默认 30 |

**话术示例**

- 去 A 点 → point=point_a
- 移动到 point_b
- 回到 home / 回到原点 / 回到零点

**JSON 示例**

```json
{
  "explain": "关节运动到 point_a",
  "skill": "move_to_named_point",
  "params": {
    "point": "point_a",
    "move_type": "movj",
    "speed_percent": 30
  }
}
```

---

### 4. move_between_points — 两点间运动

| 参数 | 说明 |
|------|------|
| from_point | 起点名 |
| to_point | 终点名 |
| move_type | movj / movl |
| speed_percent | 可选 |

**话术示例**

- 从 A 点移动到 B 点 → from_point=point_a, to_point=point_b
- 从 point_a 到 point_b
- 从 home 到 A 点

---

### 5. motion_pattern — 预置复合运动路线

底层仅调用官方 SDK 的 `MovL` / `Arc` / `Circle`，执行完回到起点。

| 参数 | 说明 |
|------|------|
| pattern | 见下表 pattern 枚举 |
| size_mm | 5～200，默认 50（方形/矩形/三角等边长） |
| radius_mm | 5～100，默认 30（圆/弧/螺旋半径） |
| height_mm | -200～200，默认 50 |
| turns | 1～5，默认 2（仅 spiral_z） |
| speed_percent | 可选，默认 30 |

**pattern 枚举与话术**

| pattern | 话术关键词 |
|---------|-----------|
| circle_xy | 画圆、圆形、整圆、XY 平面画圆 |
| circle_xz | XZ 画圆 |
| circle_yz | YZ 画圆 |
| arc_xy | 走圆弧、弧线 |
| arc_xz | XZ 圆弧 |
| arc_yz | YZ 弧线/圆弧 |
| square_xy | 走方形路线、正方形、方框 |
| rectangle_xy | 走矩形路线、矩形、长方形 |
| triangle_xy | 走三角形、三角路线 |
| diamond_xy | 走菱形 |
| cross_xy | 走十字形 |
| zigzag_x | 锯齿、折线 |
| wave_y | 波浪、波形 |
| u_shape_xy | U 型/U 形 |
| xyz_step_return | 先 X+ 再 Y+ 再 Z+ 再回到原点 |
| xz_lift_return | XZ 抬升返回 |
| yz_lift_return | YZ 抬升返回 |
| l_shape_xyz | L 型/L 形 |
| box_outline | 走箱体轮廓、盒子、立方体 |
| spiral_z | 走三维螺旋、空间螺旋、螺旋 |

**话术示例**

- 画圆 30 毫米 → pattern=circle_xy, radius_mm=30
- 走方形路线 50 毫米 → pattern=square_xy, size_mm=50
- 走三维螺旋运动 40 毫米 → pattern=spiral_z, radius_mm=40

---

### 6. set_speed — 设置速度

| 参数 | 说明 |
|------|------|
| speed_percent | 1～50 |

**话术**：速度设置为 30%、速度调到 20、慢一点(→20%)、快一点(→40%)

---

### 7. wait — 等待

| 参数 | 说明 |
|------|------|
| seconds | 0.1～10 |

**话术**：等待 2 秒、停 1.5 秒、等一下/暂停一下(→1 秒)

---

### 8. read_pose — 读当前位姿

| 参数 | 说明 |
|------|------|
| save_as | 可选，标定点名 |

**话术**：读取当前位置、查询当前位姿、记录当前位置为 home、保存当前位置为 point_a

---

### 9. stop_or_disable — 停止或下使能

| 参数 | 说明 |
|------|------|
| action | stop（默认）或 disable |

**话术**

- 停止运动 / 停住 / 急停 → action=stop
- 下使能 → action=disable

---

### 10. enable_robot — 上使能

| 参数 | 说明 |
|------|------|
| （无） | params 为空对象 {} |

**话术**：上使能、上使能机械臂

**JSON 示例**

```json
{
  "explain": "上使能机械臂",
  "skill": "enable_robot",
  "params": {}
}
```

---

## 全局安全限制

| 项目 | 限制 |
|------|------|
| 单步相对移动 | 0.1～200 mm |
| 多步相对移动 | 2～10 步，每步 0.1～200 mm |
| 复合路线边长 size_mm | 5～200 mm |
| 圆/弧/螺旋半径 radius_mm | 5～100 mm |
| 运动速度 | 默认 30%，最大 50% |
| 等待时间 | 0.1～10 秒 |

超出时 `executor` 拒绝执行，或 LLM 应拒识（skill 留空并在 explain 说明）。

---

## 命名点位（positions.json）

| 名称 | 别名 | 用途 |
|------|------|------|
| home | 原点、零点 | 回零/安全点 |
| point_a | A 点、a点 | 演示点 A |
| point_b | B 点、b点 | 演示点 B |

客户说「A 点」对应 **point_a**，不是随意坐标。

---

## 选型规则（规划时用）

1. 单轴 + 距离 → **move_relative_linear**
2. 多步「先/再/然后」且每步距离自定义 → **move_relative_sequence**
3. 去单点 / 回 home → **move_to_named_point**
4. 从一点到另一点 → **move_between_points**
5. 画圆/走方/螺旋等固定轨迹 → **motion_pattern**（不要用 sequence 拼圆）
6. 只调速度 → **set_speed**；只等待 → **wait**；只读位姿 → **read_pose**
7. 停止/下使能 → **stop_or_disable**；上使能 → **enable_robot**

**多步两种方式：**

| 方式 | 示例 | 区别 |
|------|------|------|
| move_relative_sequence | `先 x+50mm，再 y+50mm` | 自定义每步距离 |
| motion_pattern | `画圆 30 毫米` | 系统预置固定轨迹 |
| 交互模式分条输入 | 先说 X 移动，再说 Y 移动 | 每句一个 Skill |

---

## 不支持（第一版勿承诺）

| 类型 | 示例 |
|------|------|
| 视觉/抓取 | 「帮我把杯子拿过来」 |
| 意图不明 | 「随便动一下」 |
| 超大距离 | 「向 Z 移动 500 毫米」 |
| 超过 10 步 | 一条指令 11 步「先…再…」 |
| 未注册动作 | 「设置 IO 输出」「旋转工具坐标系」 |
| 随意坐标 | 编造未标定的 XYZ 绝对坐标 |

无法识别时 JSON 应为：`"skill": ""`, `"params": {}`，explain 说明原因。

---

## 执行命令（工作目录必须在项目根）

预演（默认先做）：

```powershell
.\.venv\Scripts\python nl_robot.py --dry-run "客户原话"
```

真机（用户确认后）：

```powershell
.\.venv\Scripts\python nl_robot.py "客户原话"
```

复杂话术兜底（规则识别不了时）：

```powershell
.\.venv\Scripts\python nl_robot.py --llm --dry-run "客户原话"
.\.venv\Scripts\python nl_robot.py --llm "客户原话"
```

解析结果保存在 `generated\last_plan.json`。

---

## 演示推荐话术（优先用这些）

1. 向 Z 正方向移动 100 毫米
2. 抬高 20 毫米
3. 先 x+30mm，再 y+30mm
4. 读取当前位置
5. 去 A 点
6. 从 A 点移动到 B 点
7. 画圆 30 毫米
8. 回到 home
9. 停止运动
10. 下使能 → 上使能（使能恢复演示）

**推荐演示顺序：** 抬高 20 毫米 → 先 x+30mm，再 y+30mm → 读取当前位置 → 去 A 点 → 画圆 30 毫米 → 回到 home → 停止运动
