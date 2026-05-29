# Titatit MuJoCo Sim2Sim 项目

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![ROS 2](https://img.shields.io/badge/ROS%202-Humble-green.svg)](https://docs.ros.org/en/humble/)

## 📋 项目概述

本项目旨在让 `titatit` 轮式四足机器人在 MuJoCo 物理仿真环境中稳定运行，通过部署 IsaacGym 训练的 ONNX 强化学习策略，实现 Sim2Sim（仿真到仿真）的迁移。

### 核心目标

- ✅ 在 MuJoCo 中部署 IsaacGym 训练的 ONNX 策略
- ✅ 确保 MuJoCo 模型、关节、初始姿态、控制参数与训练环境一致
- ✅ 实现稳定的状态机切换：`idle → joint_pd → rl_flat`
- ✅ 支持复杂地形场景的验证

### 工作空间

| 环境 | 路径 |
|------|------|
| 本地工作空间 | `/home/dxx/ddt_ros2_ws` |
| Docker 容器内 | `/mnt/dev` |
| 训练仓库 | `/home/dxx/quadruped-wheel-titatit-rl` |

---

## 📁 项目结构

```
ddt_ros2_ws/
├── src/ddt_ros2_control/
│   ├── controller/rl_controller/          # RL 控制器
│   │   ├── config/titatit/
│   │   │   ├── controllers.yaml          # 控制器配置
│   │   │   ├── model_6000.onnx           # ONNX 策略模型
│   │   │   └── model_gn.engine           # TensorRT 引擎（备选）
│   │   ├── launch/sim_mujoco.launch.py   # MuJoCo 启动文件
│   │   └── src/fsm/                      # 状态机实现
│   ├── simulation/mujoco_bridge/         # MuJoCo 桥接层
│   │   ├── mujoco_ros2_control/          # ROS2 控制接口
│   │   └── mujoco_sim_ros2/              # MuJoCo 主程序
│   └── urdfs/titatit_description/        # 机器人描述
│       ├── mujoco/                       # MuJoCo 模型文件
│       │   ├── robot.xml                 # MuJoCo 机器人模型
│       │   └── scene.xml                 # MuJoCo 场景（含复杂地形）
│       ├── meshes/                       # 网格资源
│       └── xacro/                        # Xacro 描述文件
```

---

## 🎯 训练信息摘要

### 训练配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 训练任务 | `wheeled_titatit` | 轮式 titatit 任务 |
| 训练配置 | `WheeledTitatitConstraintHimRoughCfg` | 约束型粗糙地形配置 |
| 时间步长 (dt) | `0.005` | 物理仿真步长 |
| Decimation | `4` | 每次控制决策的物理步数 |
| 策略频率 | `50 Hz` | 控制决策频率 |
| 物理频率 | `200 Hz` | 物理仿真频率 |
| 控制类型 | `P` | 位置控制 |
| 刚度 (stiffness) | `25` | 腿关节刚度 |
| 阻尼 (damping) | `0.625` | 腿关节阻尼 |
| Action Scale | `0.25` | 动作缩放系数 |
| Hip Scale Reduction | `0.5` | 髋关节缩放减少 |

### 轮子扭矩公式

```python
wheel_torque = 10 * action_scaled[wheel] - 0.5 * dof_vel[wheel]
```

### 训练默认关节角

根据训练配置文件 `configs/wheeled_titatit_constraint_him.py`：

```python
default_joint_angles = {
    'FL_hip_joint': 0.1,
    'RL_hip_joint': 0.1,
    'FR_hip_joint': -0.1,
    'RR_hip_joint': -0.1,

    'FL_thigh_joint': 1.0,
    'RL_thigh_joint': -0.8,
    'FR_thigh_joint': 1.0,
    'RR_thigh_joint': -0.8,

    'FL_calf_joint': -1.5,
    'RL_calf_joint': 1.5,
    'FR_calf_joint': -1.5,
    'RR_calf_joint': 1.5,

    'FL_foot_joint': 0.0,
    'RL_foot_joint': 0.0,
    'FR_foot_joint': 0.0,
    'RR_foot_joint': 0.0,
}
```

按腿部组织（hip, thigh, calf, wheel）：

```text
FL: [ 0.1,  1.0, -1.5, 0.0]
FR: [-0.1,  1.0, -1.5, 0.0]
RL: [ 0.1, -0.8,  1.5, 0.0]
RR: [-0.1, -0.8,  1.5, 0.0]
```

ROS2 控制器中的数组形式（FL, FR, RL, RR 顺序）：

```yaml
default_joint_angles: [0.1, 1.0, -1.5, 0.0, -0.1, 1.0, -1.5, 0.0, 0.1, -0.8, 1.5, 0.0, -0.1, -0.8, 1.5, 0.0]
```

### 关节重排映射 (Reindex)

训练侧使用 Unitree 风格顺序 `FR, FL, RR, RL`，而 ROS 控制器使用 `FL, FR, RL, RR`。

```python
reindex = [4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11]
```

**重要**：这是 Sim2Sim 部署的关键参数，错误会导致策略控制的腿和实际控制的腿不一致。

---

## 🚀 部署说明

### ONNX 模型

当前使用的模型文件：

```bash
src/ddt_ros2_control/controller/rl_controller/config/titatit/model_6000.onnx
```

### 模型输入/输出规格

| 名称 | 类型 | 形状 | 说明 |
|------|------|------|------|
| `obs` | 输入 | `[1, 57]` | 当前观测 |
| `obs_hist` | 输入 | `[1, 10, 57]` | 观测历史 |
| `actions` | 输出 | `[1, 16]` | 16 个关节的动作 |

### 控制配置

配置文件位置：

```bash
src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml
```

关键配置项：

```yaml
rl_flat:
  default_joint_angles:
    FL: [0.1, 1.0, -1.5, 0.0]
    FR: [-0.1, 1.0, -1.5, 0.0]
    RL: [0.1, -0.8, 1.5, 0.0]
    RR: [-0.1, -0.8, 1.5, 0.0]
  
  # RL gains（对齐训练）
  kp: [25, 25, 25, 10, 25, 25, 25, 10, 25, 25, 25, 10, 25, 25, 25, 10]
  kd: [0.625, 0.625, 0.625, 0.5, 0.625, 0.625, 0.625, 0.5, 0.625, 0.625, 0.625, 0.5, 0.625, 0.625, 0.625, 0.5]
  
  # 关节重排
  reindex: [4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11]
  obs_reindex: [4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11]
  action_reindex: [4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11]
  re_sign: [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
  
  # 动作缩放（对齐训练：基础0.25，髋关节减半至0.125）
  action_scales: [0.125, 0.25, 0.25, 0.25, 0.125, 0.25, 0.25, 0.25, 0.125, 0.25, 0.25, 0.25, 0.125, 0.25, 0.25, 0.25]
  
  # 动作滤波（注意：0.8 表示保留80%的新动作）
  action_filter_alpha: 0.8
```

---

## 🏃 启动指南

### 编译

在 Docker 容器内：

```bash
cd /mnt/dev
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select titatit_description mujoco_sim_ros2 mujoco_ros2_control rl_controller
source install/setup.bash
```

### 基础启动

默认启动（带 GUI）：

```bash
ros2 launch rl_controller sim_mujoco.launch.py robot:=titatit
```

### 常用启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `headless` | `false` | 是否无头模式（无 GUI） |
| `startup_pause_sec` | `6.0` | 启动暂停时间（秒） |
| `rl_warmup_sec` | `3.0` | RL 预热时间（秒） |
| `cmd_vel_x` | `1.0` | 前进速度命令 |
| `autostart` | `true` | 是否自动发布状态切换命令 |

### Headless 模式启动

```bash
ros2 launch rl_controller sim_mujoco.launch.py robot:=titatit headless:=true
```

### 自定义参数启动

```bash
ros2 launch rl_controller sim_mujoco.launch.py \
  robot:=titatit \
  headless:=false \
  startup_pause_sec:=8.0 \
  rl_warmup_sec:=3.0 \
  cmd_vel_x:=0.0
```

### 零速度回归测试（45秒超时）

```bash
timeout 45s ros2 launch rl_controller sim_mujoco.launch.py \
  robot:=titatit \
  headless:=true \
  startup_pause_sec:=8.0 \
  rl_warmup_sec:=3.0 \
  cmd_vel_x:=0.0
```

### 启动流程

```
1. MuJoCo 物理仿真启动
2. ROS2 控制器和 broadcaster 加载
3. 进入 idle 状态（机器人被支撑）
4. 等待 startup_pause_sec 秒
5. 发布 joint_pd 命令（机器人移动到训练默认姿态）
6. 等待关节误差收敛
7. 发布 cmd_vel 命令
8. 发布 rl_0 命令（RL 接管）
9. RL 策略开始控制
```

---

## 🔧 已修复的核心问题

### 1. ✅ MuJoCo 启动时控制器未及时介入
- **问题**：MuJoCo 物理已运行，但控制器未完全加载，导致机器人悬空下落
- **修复**：增加启动暂停、优化加载时序、延长 spawner 超时时间

### 2. ✅ MuJoCo ros2_control 扭矩写入路径错误
- **问题**：对 actuator joint 应写 `mj_data_->ctrl`，但错误地写入了 `qfrc_applied`
- **修复**：注册 actuator id，正确写入 `ctrl[]`，读取 `actuator_force`

### 3. ✅ MuJoCo sensor 注册索引错误
- **问题**：使用 `sensor_index` 导致多 sensor 时越界或绑定错误
- **修复**：改为使用 `back()` 获取刚 push 的 sensor data

### 4. ✅ 初始姿态没有严格使用 MuJoCo home keyframe
- **问题**：依赖 ros2_control 初值，不能保证与训练默认姿态一致
- **修复**：优先读取并应用 MuJoCo `home` keyframe

### 5. ✅ idle 状态没有支撑机器人
- **问题**：`idle` 状态机器人自由下落或姿态偏移
- **修复**：在 `idle` 中使用 `joint_pd.target_jpos` 主动支撑

### 6. ✅ joint_pd 目标和日志不足
- **问题**：`joint_pd` 保持当前姿态而非训练默认姿态，缺少诊断日志
- **修复**：新增 `target_jpos` 参数，增加低频日志

### 7. ✅ RL 策略配置与训练不一致
- **问题**：默认角、PD gains、action scale 等与训练配置不一致
- **修复**：全面对齐训练参数，包括 wheel torque 公式

### 8. ✅ RL 动作滤波语义错误
- **问题**：滤波实现与训练不一致（对已滤波动作继续滤波）
- **修复**：使用原始动作历史做滤波，严格匹配训练代码

### 9. ✅ RL 观测/动作关节顺序错误 ⚠️ **核心问题**
- **问题**：训练使用 `FR, FL, RR, RL` 顺序，部署错误使用 identity
- **修复**：设置正确的 reindex 映射，这是 RL 接管后失稳的核心原因

### 10. ✅ ONNX 输入/输出处理增强
- **问题**：默认假设固定输入形式，不够稳健
- **修复**：根据输入数量自动选择单/双输入模式，增加 shape 检查

### 11. ✅ MuJoCo 模型和资源安装
- **问题**：`titatit_description` 未完整安装资源
- **修复**：安装 `mujoco`、`meshes` 等目录，修复 CMake 判断

### 12. ✅ MuJoCo robot.xml 清理
- **问题**：Joint 的 `ref` 和 `home qpos` 同时带非零值，造成混淆
- **修复**：统一 `ref` 为 `0`，使用 `home` keyframe 存储初始姿态

---



## 📝 相关文件清单

### RL Controller

- `src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml`
  - 对齐训练参数、模型路径、PD gains、action scale、关节重排
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/common/RobotParameters.h`
  - 新增参数定义
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_RL.h`
  - 增加 control action buffer、raw action history
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_RL.cpp`
  - 修复 ONNX 输入、动作滤波、wheel torque、观测/动作顺序
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_JointPD.cpp`
  - 使用目标站姿、wheel 特殊处理、增加日志
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_Passive.cpp`
  - idle 阶段主动支撑机器人
- `src/ddt_ros2_control/controller/rl_controller/launch/sim_mujoco.launch.py`
  - 重构 MuJoCo launch、自动状态切换

### MuJoCo Bridge

- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system.hpp`
  - 保存 actuator id
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_system.cpp`
  - 修复 actuator effort 读写、sensor 注册、home keyframe 初始化
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_ros2_control.cpp`
  - 支持从参数读取 `robot_description`
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_sim_ros2/src/main.cc`
  - 增加 headless 运行模式和 startup pause

### Robot Description

- `src/ddt_ros2_control/urdfs/titatit_description/CMakeLists.txt`
  - 安装 MuJoCo 和 mesh 资源
- `src/ddt_ros2_control/urdfs/titatit_description/xacro/robot.xacro`
  - 默认 `hw_env:=mujoco`
- `src/ddt_ros2_control/urdfs/titatit_description/xacro/ros2control.xacro`
  - MuJoCo 硬件插件配置
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/robot.xml`
  - MuJoCo robot model（home keyframe、actuator、sensor）
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/scene.xml`
  - MuJoCo scene（复杂地形）

---

## 🔍 日志解读指南

### 关键指标说明

| 指标 | 正常范围 | 异常表现 |
|------|----------|----------|
| `q_err_norm` | `< 0.5` | 过大说明关节偏差 |
| `gravity` | `(0, 0, -1)` | 偏离说明机身倾斜 |
| `dq_norm` | `5-15` | 过大说明运动不稳定 |
| `pos_err_norm` | `< 0.1` | 过大说明跟踪误差大 |
| `tau_norm` | `10-30` | 过大说明扭矩过大 |
| `wheel_vel` | `5-15` | 与命令对应 |

### 典型问题排查

**问题 1：RL 接管后立刻趴地抽搐**
- 检查：关节顺序（reindex）是否正确
- 日志：观察 `q_err_norm` 是否突然增大

**问题 2：机器人前栽**
- 检查：重力向量 `gravity` 是否偏离 `(0, 0, -1)`
- 日志：观察 `projected gravity` 在 joint_pd 阶段的变化

**问题 3：轮子不转或转速异常**
- 检查：wheel torque 公式是否正确实现
- 日志：观察 `wheel_vel` 和 `action norm`

---

## 📚 参考资料

- [IsaacGym 文档](https://developer.nvidia.com/isaac-gym)
- [MuJoCo 文档](https://mujoco.readthedocs.io/)
- [ROS 2 Humble 文档](https://docs.ros.org/en/humble/)
- [ONNX Runtime 文档](https://onnxruntime.ai/docs/)

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📧 联系方式

如有问题，请通过 GitHub Issues 联系。

---

**最后更新**：2026-05-28