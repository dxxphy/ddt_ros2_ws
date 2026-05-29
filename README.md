# Titatit MuJoCo Sim2Sim 项目

## 📋 项目概述

本项目旨在让 `titatit` 轮式四足机器人在 MuJoCo 物理仿真环境中稳定运行，通过部署 IsaacGym 训练的 ONNX 强化学习策略，实现 Sim2Sim（仿真到仿真）的迁移。

## 🔧 修复说明

本项目基于 [ddt_ros2_control](https://github.com/DDTRobot/ddt_ros2_control) 进行开发。

由于官方对 MuJoCo 平台 Sim2Sim 的支持尚不完善，存在以下问题：
- Controller 与 MuJoCo 不适配
- MuJoCo 下的 Titatit asset 缺失

为了解决这些问题，我参考了 [官方训练仓库](https://github.com/DDTRobot/tita_rl) 中提供的 titatit asset，并对其进行了适配性修改，使其能够在 MuJoCo 仿真环境中稳定运行，同时修改controller，使各参数配置与训练参数对齐。

### 核心目标

- ✅ 在 MuJoCo 中部署 IsaacGym 训练的 ONNX 策略
- ✅ 确保 MuJoCo 模型、关节、初始姿态、控制参数与训练环境一致
- ✅ 实现稳定的状态机切换：`idle → joint_pd → rl_flat`
- ✅ 支持复杂地形场景的验证

---

### 环境配置（Docker）

#### 下载docker镜像
```
docker pull registry.cn-hangzhou.aliyuncs.com/ddt_robot/run_ddt_tita:v1.0
```

#### 启动 docker

```
sudo docker run -v path/above/your/project:/mnt/dev -w /mnt/dev --rm  --gpus all --net=host --privileged -e DISPLAY=$DISPLAY -e QT_X11_NO_MITSHM=1  -e CUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda -it registry.cn-hangzhou.aliyuncs.com/ddt_robot/run_ddt_tita:v1.0

# 举个例子：
docker run -it \
  --name tita_container \
  -v ~/ddt_ros2_ws:/mnt/dev \
  -v /home/dxx/TensorRT-10.13.0.35:/opt/tensorrt \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -w /mnt/dev \
  --gpus '"device=1"' \
  --net=host \
  --privileged \
  -e DISPLAY=$DISPLAY \
  -e QT_X11_NO_MITSHM=1 \
  -e CUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda \
  -e MUJOCO_GL=glfw \
  registry.cn-hangzhou.aliyuncs.com/ddt_robot/run_ddt_tita:v1.0
```

#### 进入容器终端
```
docker exec -it tita_container /bin/bash
```
#### 构建项目空间  
以下命令展示了所有可行的编译命令，根据你的实际需要选择必要的组件进行编译。
```bash
# 创建并进入工作空间
mkdir -p ~/ddt_ros2_ws && cd ~/ddt_ros2_ws
# 将下载的仓库ddt_ros2_control放置于 ~/ddt_ros2_ws/并且重命名为src
mv ddt_ros2_control src
# 若使用mujoco，执行下方
git clone -b 3.3.0 https://github.com/google-deepmind/mujoco.git
# 构建
cd ~/ddt_ros2_ws
# 编译
colcon build --symlink-install --packages-up-to rl_controller d1_description d1h_description tita_description titatit_description teleop_command keyboard_controller mujoco_bridge # 其中mujoco_bridge可替换为gazebo_bridge，webots_bridge
# 载入环境
source install/setup.bash
# 确保使用nvidia gpu进行渲染而非mesa
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export __NV_PRIME_RENDER_OFFLOAD=1
```

---

### 工作空间

| 环境 | 路径 |
|------|------|
| 本地工作空间 | `/home/dxx/ddt_ros2_ws` |
| Docker 容器内 | `/mnt/dev` |
| 训练仓库 | `/home/dxx/quadruped-wheel-titatit-rl` |

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

### 自定义参数启动

```bash
ros2 launch rl_controller sim_mujoco.launch.py \
  robot:=titatit \
  headless:=false \
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


---

## 🚀 部署说明

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


## 📚 参考资料

- [IsaacGym 文档](https://developer.nvidia.com/isaac-gym)
- [MuJoCo 文档](https://mujoco.readthedocs.io/)
- [ROS 2 Humble 文档](https://docs.ros.org/en/humble/)
- [ONNX Runtime 文档](https://onnxruntime.ai/docs/)

---
