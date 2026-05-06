# Titatit MuJoCo Sim2Sim 修复总结

日期：2026-05-06

## 总体结果

本轮工作围绕 `titatit` 在 MuJoCo 中的 sim2sim 部署问题展开。最初现象包括：启动后悬空下落、`joint_pd` 前倾或翻倒、RL 接管后趴地抽搐、走一段后倒下。当前主要问题已修复：

- `idle -> joint_pd -> rl_flat` 的启动和状态切换流程已可稳定执行。
- `joint_pd` 能在 RL 接管前把机器人保持在接近训练默认姿态。
- RL 接管后不再立刻趴地抽搐。
- 修正了策略观测/动作关节顺序错误，这是 RL 接管后失稳的核心原因。
- 恢复了原复杂地形场景，保留策略针对复杂地形验证的环境。

## 已修复的问题

### 1. MuJoCo 启动时控制器未及时介入

原问题：

- MuJoCo 物理已经开始运行，但 RL 控制器和 broadcaster 尚未完全加载。
- 机器人在 `idle` 阶段基本没有有效支撑，导致启动悬空下落、姿态偏移。
- `joint_pd` 和 `rl_0` 命令发布时间与控制器激活时序不可靠。

修复：

- `sim_mujoco.launch.py` 增加 `headless`、`startup_pause_sec`、`autostart`、`cmd_vel_x`、`rl_warmup_sec` 参数。
- MuJoCo 启动时传入 `robot_description`，并使用 `hw_env:=mujoco`。
- `joint_state_broadcaster` 和 RL 控制器并行加载。
- RL 控制器激活后再发布 `joint_pd`，之后延时发布 `cmd_vel` 和 `rl_0`。
- spawner 增加较长 switch timeout，避免启动阶段服务短暂不可用导致加载失败。

相关文件：

- `src/ddt_ros2_control/controller/rl_controller/launch/sim_mujoco.launch.py`
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_sim_ros2/src/main.cc`
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_ros2_control.cpp`
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_ros2_control.hpp`

### 2. MuJoCo ros2_control 扭矩写入路径错误

原问题：

- MuJoCo 模型使用 actuator，但桥接层主要写 `qfrc_applied`。
- 对 actuator joint，应写 `mj_data_->ctrl[actuator_id]`，否则控制效果与模型定义不一致。
- effort 读取也没有优先读取 actuator force。

修复：

- 注册 joint 时记录对应 MuJoCo actuator id。
- 写控制命令时，有 actuator 则写 `mj_data_->ctrl`，同时清掉对应 `qfrc_applied`。
- 读取 effort 时，有 actuator 则读取 `mj_data_->actuator_force`。

相关文件：

- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_system.cpp`
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system.hpp`

### 3. MuJoCo sensor 注册索引错误

原问题：

- FT/IMU sensor 注册时使用 `vector.at(sensor_index)`，但 `sensor_index` 是 hardware info 中的 sensor 下标，不等价于当前 vector 的下标。
- 多 sensor 或 sensor 顺序变化时可能越界或绑定错误。

修复：

- 改为 `ft_sensor_data_.back()` 和 `imu_sensor_data_.back()` 获取刚 push 的 sensor data。

相关文件：

- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_system.cpp`

### 4. 初始姿态没有严格使用 MuJoCo home keyframe

原问题：

- 初始姿态依赖 ros2_control state 初值，不能保证与 MuJoCo XML 的 `home` keyframe 一致。
- 起步姿态与训练默认姿态存在偏差。

修复：

- `MujocoSystem::set_initial_pose()` 优先读取并应用 MuJoCo `home` keyframe。
- 应用后执行 `mj_forward()`，并打印每个 joint 的 qpos/qvel，便于确认初始状态。

相关文件：

- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_system.cpp`
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/robot.xml`

### 5. idle 状态没有支撑机器人

原问题：

- `idle` 状态只给阻尼或弱控制，启动早期机器人会自由下落或明显姿态偏移。

修复：

- `FSMState_Passive` 在 `idle` 下优先使用 `joint_pd.target_jpos` 和 `joint_pd` gains 支撑机器人。
- 如没有目标姿态，则 hold 进入 idle 时的当前关节位置。
- 增加从 `idle` 直接处理 `rl_N` 命令的能力。

相关文件：

- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_Passive.cpp`
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_Passive.h`

### 6. joint_pd 目标和日志不足

原问题：

- `joint_pd` 原来保持进入状态时的当前姿态，不一定回到训练默认站姿。
- 无法直接看到 RL 接管前的关节误差和机体姿态。

修复：

- 新增 `joint_pd.target_jpos` 参数，目标为训练默认姿态。
- `joint_pd` 使用目标姿态而不是当前姿态。
- 对 wheel joint 避免位置锁死。
- 增加低频日志：`q_err_norm` 和重力向量。
- 适当调整 `joint_pd` gains，使 RL 接管前误差降低到可控范围。

相关文件：

- `src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml`
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_JointPD.cpp`
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_JointPD.h`
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/common/RobotParameters.h`
- `src/ddt_ros2_control/controller/rl_controller/src/rl_controller_node.cpp`

### 7. RL 策略配置与训练不一致

原问题：

- 部署端使用的默认角、PD gains、action scale、torque limit 等与训练配置不一致。
- wheel torque 路径与 IsaacGym 训练公式不完全一致。

修复：

- `rl_flat` 使用 `model_6000.onnx`，输出名为 `actions`。
- 更新默认关节角为训练配置：
  - FL/FR thigh `1.0`，calf `-1.5`
  - RL/RR thigh `-0.8`，calf `1.5`
- RL gains 对齐训练：leg `kp=25`、`kd=0.625`，wheel `kp=10`、`kd=0.5`。
- torque limit 对齐为 leg `55`、wheel `10`。
- action scale 对齐训练，并保留 hip scale reduction 效果。
- wheel torque 按训练公式实现：`10 * action_scaled - 0.5 * dof_vel`。
- 增加可选 `torque_control` 参数，支持显式扭矩模式调试。

相关文件：

- `src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml`
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_RL.cpp`
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/common/RobotParameters.h`
- `src/ddt_ros2_control/controller/rl_controller/src/rl_controller_node.cpp`

### 8. RL 动作滤波语义错误

原问题：

- 训练中滤波是：`0.8 * 当前原始动作 + 0.2 * 上一帧原始动作`。
- 部署端一度实现成对“上一帧已滤波动作”继续滤波，动作时序与训练不一致。

修复：

- 新增 `last_raw_control_action_vec_`。
- 部署端严格使用原始动作历史做滤波，匹配训练代码。

相关文件：

- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_RL.cpp`
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_RL.h`

### 9. RL 观测/动作关节顺序错误

原问题：

- 训练资产和策略使用的是 Unitree 风格顺序：`FR, FL, RR, RL`。
- ROS 控制器关节顺序是：`FL, FR, RL, RR`。
- 部署端曾错误地按 identity 处理，导致策略看到的腿和实际控制的腿不一致。
- 这是 RL 接管后“站很短时间就趴地抽搐”的核心原因。

修复：

- 将 `reindex`、`obs_reindex`、`action_reindex` 设为：
  - `[4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11]`
- 拆分 observation reindex 和 action reindex，便于后续单独调试。
- `last_actions` 保持训练语义：记录网络原始输出动作，而不是控制顺序动作。

相关文件：

- `src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml`
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_RL.cpp`
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_RL.h`

### 10. ONNX 输入/输出处理增强

原问题：

- 部署端默认假设固定输入形式，不能稳健兼容单输入/双输入 ONNX。
- 输出名和 shape 处理不够明确。

修复：

- ONNX loader 启用模型信息读取。
- 根据输入数量选择单输入 history 或双输入 `obs + obs_hist`。
- 明确设置输出名 `actions`。
- 增加输入 shape 检查，避免 history 配置和模型输入尺寸不一致。

相关文件：

- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_RL.cpp`
- `src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml`

### 11. MuJoCo 模型和资源安装

原问题：

- `titatit_description` 未完整安装 MuJoCo XML、mesh 等资源，launch 后可能找不到资源。
- `robot.xacro` 默认环境不是 MuJoCo。
- `ros2control.xacro` 没有针对 `hw_env:=mujoco` 选择 `MujocoSystem`。

修复：

- `titatit_description` 安装 `mujoco`、`meshes` 等目录。
- `robot.xacro` 默认 `hw_env` 改为 `mujoco`。
- `ros2control.xacro` 增加 MuJoCo 硬件插件：`mujoco_ros2_control/MujocoSystem`。
- 增加 `tita_description` exec dependency，以支持 titatit 描述继承/资源引用。
- 其他 description 包的 `ROS_VERSION` 判断改为字符串判断，避免 CMake 在环境变量为空或非数值时出错。

相关文件：

- `src/ddt_ros2_control/urdfs/titatit_description/CMakeLists.txt`
- `src/ddt_ros2_control/urdfs/titatit_description/package.xml`
- `src/ddt_ros2_control/urdfs/titatit_description/xacro/robot.xacro`
- `src/ddt_ros2_control/urdfs/titatit_description/xacro/ros2control.xacro`
- `src/ddt_ros2_control/urdfs/d1_description/CMakeLists.txt`
- `src/ddt_ros2_control/urdfs/d1h_description/CMakeLists.txt`
- `src/ddt_ros2_control/urdfs/tita_description/CMakeLists.txt`
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/robot.xml`
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/scene.xml`
- `src/ddt_ros2_control/urdfs/titatit_description/meshes/`
- `src/ddt_ros2_control/urdfs/titatit_description/dae/`

### 12. MuJoCo robot.xml 清理

原问题：

- Joint 的 `ref` 和 `home qpos` 同时带非零默认姿态，会造成控制器读数、几何默认姿态和 MuJoCo 关节 reference 混用。

修复：

- `robot.xml` 中 16 个 actuated joint 的 `ref` 统一为 `0`。
- 使用 `home` keyframe 存储初始站立姿态。

相关文件：

- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/robot.xml`

## 已恢复的内容

用户确认策略本身针对复杂地形训练，因此已恢复 `scene.xml` 中原有复杂地形障碍：

- `x=1.5` 和 `x=2.0` 的低障碍。
- `x=2.8` 到 `x=4.4` 的阶梯/障碍序列。

相关文件：

- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/scene.xml`

## 当前仍保留的诊断日志

为了后续继续定位 sim2sim 问题，当前保留了以下低频日志：

- `FSMState_JointPD`：
  - `q_err_norm`
  - projected gravity
- `FSMState_RL enter`：
  - gravity
  - quaternion
  - q norm
  - default q norm
  - non-wheel joint error norm
  - command
  - 每个 joint 的 q/default/delta
- `FSMState_RL control`：
  - q norm
  - dq norm
  - position error norm
  - torque norm
  - wheel velocities
- `FSMState_RL`：
  - action norm
  - control action norm
  - gravity
  - command

这些日志可在稳定后再清理或降级为 debug。

## 关键验证结果

在 Docker 容器 `tita_container_new` 中完成过编译和 headless 验证。

编译命令：

```bash
cd /mnt/dev
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select titatit_description mujoco_sim_ros2 mujoco_ros2_control rl_controller
```

零速度命令回归：

```bash
source install/setup.bash
timeout 45s ros2 launch rl_controller sim_mujoco.launch.py robot:=titatit headless:=true startup_pause_sec:=8.0 rl_warmup_sec:=3.0 cmd_vel_x:=0.0
```

结果：

- RL 接管后不再趴地抽搐。
- `gravity` 和 `dq_norm` 保持在合理范围。
- 证明主要问题不是策略本身，而是部署侧顺序和控制语义不一致。

前进命令回归：

```bash
source install/setup.bash
timeout 60s ros2 launch rl_controller sim_mujoco.launch.py robot:=titatit headless:=true startup_pause_sec:=8.0 rl_warmup_sec:=3.0 cmd_vel_x:=1.0
```

结果：

- 修正关节顺序后，RL 接管行为明显改善。
- 平地验证中不再出现原先那种接管后立即翻倒/趴地抽搐。
- 复杂地形下是否能持续通过障碍，取决于策略训练能力、地形设置和速度命令，不再是之前的部署顺序错误问题。

## 关于初始悬空

当前判断：

- 只要进入 RL 前 `joint_pd` 已经把机器人姿态和速度收敛，初始轻微悬空下落不是当前主要问题。
- 它主要影响启动观感和初始瞬态，不是 RL 接管后崩溃的核心原因。
- 如果后续发现“第一次启动容易失败，重启或重置后正常”，再继续精调 MuJoCo `home` 高度或接触几何。

## 新增或使用的模型/资源

- `src/ddt_ros2_control/controller/rl_controller/config/titatit/model_6000.onnx`
- `src/ddt_ros2_control/controller/rl_controller/config/titatit/model_gn.engine`
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/`
- `src/ddt_ros2_control/urdfs/titatit_description/meshes/`
- `src/ddt_ros2_control/urdfs/titatit_description/dae/`

其中当前 `controllers.yaml` 使用的是 `model_6000.onnx`。

## 修改文件清单

### RL controller

- `src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml`
  - 对齐训练参数、模型路径、PD gains、action scale、关节重排和启动目标姿态。
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/common/RobotParameters.h`
  - 增加 `joint_pd.target_jpos`、`action_filter_alpha`、`torque_control`、`obs_reindex`、`action_reindex` 参数。
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_RL.h`
  - 增加 control action buffer、raw action history、独立 reindex 函数。
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_RL.cpp`
  - 修复 ONNX 输入、动作滤波、wheel torque、观测/动作顺序、RL 进入和控制日志。
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_JointPD.h`
  - 增加日志计数器。
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_JointPD.cpp`
  - 使用目标站姿、wheel 特殊处理、增加误差和姿态日志。
- `src/ddt_ros2_control/controller/rl_controller/include/rl_controller/fsm/FSMState_Passive.h`
  - 增加 idle hold 姿态缓存。
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSMState_Passive.cpp`
  - idle 阶段主动支撑机器人，并允许 `rl_N` 转换。
- `src/ddt_ros2_control/controller/rl_controller/src/rl_controller_node.cpp`
  - 读取新增参数。
- `src/ddt_ros2_control/controller/rl_controller/src/fsm/FSM.cpp`
  - 配合 FSM 日志和状态切换诊断。
- `src/ddt_ros2_control/controller/rl_controller/launch/sim_mujoco.launch.py`
  - 重构 MuJoCo launch、headless、startup pause、自动状态切换和命令发布。

### MuJoCo bridge

- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system.hpp`
  - 保存 actuator id。
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_system.cpp`
  - 修复 actuator effort 读写、sensor 注册、home keyframe 初始化。
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_ros2_control.hpp`
  - 增加 initialized 标志，避免未初始化时 update。
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_ros2_control/src/mujoco_ros2_control.cpp`
  - 支持从参数读取 `robot_description`，增强析构和初始化保护。
- `src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_sim_ros2/src/main.cc`
  - 增加 headless 运行模式和 startup pause。

### Robot description

- `src/ddt_ros2_control/urdfs/titatit_description/CMakeLists.txt`
  - 安装 MuJoCo 和 mesh 资源。
- `src/ddt_ros2_control/urdfs/titatit_description/package.xml`
  - 增加 ROS2 依赖。
- `src/ddt_ros2_control/urdfs/titatit_description/xacro/robot.xacro`
  - 默认 `hw_env:=mujoco`。
- `src/ddt_ros2_control/urdfs/titatit_description/xacro/ros2control.xacro`
  - `hw_env:=mujoco` 时使用 `mujoco_ros2_control/MujocoSystem`。
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/robot.xml`
  - MuJoCo robot model，包含 home keyframe、actuator、sensor 和 collision。
- `src/ddt_ros2_control/urdfs/titatit_description/mujoco/scene.xml`
  - MuJoCo scene，当前已恢复复杂地形。
- `src/ddt_ros2_control/urdfs/titatit_description/meshes/`
  - MuJoCo mesh 资源。
- `src/ddt_ros2_control/urdfs/titatit_description/dae/`
  - 可视化资源。

### 其他 description 包

- `src/ddt_ros2_control/urdfs/d1_description/CMakeLists.txt`
- `src/ddt_ros2_control/urdfs/d1h_description/CMakeLists.txt`
- `src/ddt_ros2_control/urdfs/tita_description/CMakeLists.txt`

修改目的：

- 避免 `$ENV{ROS_VERSION}` 为空或非数值时 CMake 条件判断出错。

