# Skill 与话术（OpenClaw 知识库用）

> 本文件给 OpenClaw **知识库**使用。系统行为以 `openclaw_system_prompt.txt` 为准。

## 项目路径

```
Z:\Cursor_contents\cobot+AI应用
```

Python 代码已在该目录，**不要**在对话里重新生成控制程序。

---

## Skill 白名单

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

### 2. move_to_named_point — 移动到命名点

| 参数 | 说明 |
|------|------|
| point | home / point_a / point_b |
| move_type | movj（默认）或 movl |
| speed_percent | 可选，默认 30 |

**话术示例**

- 去 A 点 → point=point_a
- 移动到 point_b
- 回到 home

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

### 3. move_between_points — 两点间运动

| 参数 | 说明 |
|------|------|
| from_point | 起点名 |
| to_point | 终点名 |
| move_type | movj / movl |
| speed_percent | 可选 |

**话术示例**

- 从 A 点移动到 B 点 → from_point=point_a, to_point=point_b
- 从 point_a 到 point_b

---

### 4. set_speed — 设置速度

| 参数 | 说明 |
|------|------|
| speed_percent | 1～50 |

**话术**：速度设置为 30%、速度调到 20

---

### 5. wait — 等待

| 参数 | 说明 |
|------|------|
| seconds | 0.1～10 |

**话术**：等待 2 秒、停 1.5 秒

---

### 6. read_pose — 读当前位姿

| 参数 | 说明 |
|------|------|
| save_as | 可选，标定点名 |

**话术**：读取当前位置、记录当前位置为 home

---

### 7. stop_or_disable — 停止或下使能

| 参数 | 说明 |
|------|------|
| action | stop（默认）或 disable |

**话术**：停止运动、下使能

---

## 全局安全限制

- 单次相对移动最大 **200mm**
- 速度最大 **50%**，默认 **30%**
- 等待最长 **10** 秒

超出时拒绝执行或向用户说明需改话术。

---

## 命名点位（positions.json）

| 名称 | 用途 |
|------|------|
| home | 回零/安全点 |
| point_a | 演示点 A |
| point_b | 演示点 B |

客户说「A 点」对应 **point_a**，不是随意坐标。

---

## 不支持（第一版勿承诺）

- 抓取、视觉、「帮拿杯子」
- 单次移动超过 200mm
- 随意编坐标

---

## 演示推荐话术（优先用这些）

1. 向 Z 正方向移动 100 毫米
2. 抬高 20 毫米
3. 去 A 点
4. 从 A 点移动到 B 点
5. 速度设置为 30%
6. 停止运动
