# Titatit MuJoCo Sim2Sim 当前任务总结

## 1. 当前目标

工作空间：

```bash
/home/dxx/ddt_ros2_ws
```

Docker 内对应路径：

```bash
/mnt/dev
```

目标是让 `titatit` 机器人在 MuJoCo 中使用 IsaacGym 训练出的 ONNX 策略稳定运行，实现 sim2sim。当前重点不是 robot viewer，而是 MuJoCo 里的模型、关节、初始姿态、控制参数和训练策略输入输出的一致性。

官方 xacro 路径如下，原则上不要修改：

```bash
src/ddt_ros2_control/urdfs/titatit_description/xacro
```

MuJoCo 相关修改应尽量集中在：

```bash
src/ddt_ros2_control/urdfs/titatit_description/mujoco
src/ddt_ros2_control/controller/rl_controller
src/ddt_ros2_control/simulation/mujoco_bridge
```

## 2. 训练侧信息

训练仓库：

```bash
/home/dxx/quadruped-wheel-titatit-rl
```

训练入口：

```bash
/home/dxx/quadruped-wheel-titatit-rl/train.py
```

训练任务：

```text
wheeled_titatit
```

训练配置：

```text
WheeledTitatitConstraintHimRoughCfg
```

训练使用的模型资源：

```bash
/home/dxx/quadruped-wheel-titatit-rl/resources/titati
```

训练默认关节角：

```text
FL: [ 0.1,  1.0, -1.5, 0.0]
FR: [-0.1,  1.0, -1.5, 0.0]
RL: [ 0.1, -0.8,  1.5, 0.0]
RR: [-0.1, -0.8,  1.5, 0.0]
```

训练控制参数：

```text
dt = 0.005
decimation = 4
policy rate = 50 Hz
physics rate = 200 Hz
control_type = P
stiffness = 25
damping = 0.625
action_scale = 0.25
hip_scale_reduction = 0.5
wheel torque = 10 * action_scaled[wheel] - 0.5 * dof_vel[wheel]
```

训练侧 reindex：

```text
[4,5,6,7,0,1,2,3,12,13,14,15,8,9,10,11]
```

这个 reindex 后续需要重点核对，因为当前 MuJoCo 控制侧很可能存在关节顺序、符号、默认角或 qpos/ref 不一致问题。

## 3. ONNX 部署状态

ONNX 和 engine 文件已经放在：

```bash
src/ddt_ros2_control/controller/rl_controller/config/titatit/
```

当前优先使用 ONNX。

ONNX 已能成功加载，运行时输出过如下信息：

```text
InputName: obs       Shape: 1 57      Size: 57
InputName: obs_hist  Shape: 1 10 57   Size: 570
OutputName: actions  Shape: 1 16      Size: 16
```

`output_name` 当前使用：

```text
actions
```

## 4. 当前主要文件状态

启动文件：

```bash
src/ddt_ros2_control/controller/rl_controller/launch/sim_mujoco.launch.py
```

当前启动逻辑：

```text
先 joint_pd
再发布 cmd_vel
再切换 rl_0
```

当前默认参数：

```text
startup_pause_sec = 6.0
rl_warmup_sec = 3.0
cmd_vel_x = 1.0
```

控制配置：

```bash
src/ddt_ros2_control/controller/rl_controller/config/titatit/controllers.yaml
```

当前关键状态：

```text
joint_pd.target_jpos = 训练默认关节角
rl_flat.default_joint_angles = 训练默认关节角
reindex = identity
obs_reindex = identity
action_reindex = identity
re_sign = 全 1.0
```

MuJoCo 模型：

```bash
src/ddt_ros2_control/urdfs/titatit_description/mujoco/robot.xml
```

当前 `home qpos` 已恢复到：

```xml
<key name="home" qpos="0 0 0.4948 1 0 0 0 -0.1 1.0 -1.5 0 0.1 1.0 -1.5 0 -0.1 -0.8 1.5 0 0.1 -0.8 1.5 0"/>
```

MuJoCo 主程序：

```bash
src/ddt_ros2_control/simulation/mujoco_bridge/mujoco_sim_ros2/src/main.cc
```

之前尝试过强制 `ResetToHomeKeyframe(...)`，后来已撤回。当前回到普通 `mj_forward(m, d)` 路径。

## 5. 已完成工作

1. 解决了 MuJoCo GUI / X11 / GLFW 相关问题，现在 MuJoCo 窗口可以打开。
2. 解决了 `libglfw.so.3` 路径问题。
3. 基于 IsaacGym 训练资源重建过 MuJoCo 视觉模型，中间连接件和轮子视觉明显改善。
4. ONNX 策略已能加载。
5. MuJoCo actuator 的 `ctrl[]` 写入路径已修复，控制面板和日志中能看到控制量变化，说明控制确实进入了 MuJoCo。
6. `startup_pause_sec` 已从 3 秒调整到 6 秒。
7. 增加过调试日志，用来打印：
   - RL enter 时的 gravity、quat、q_norm、default_q_norm、q_err_norm_no_wheel、command
   - RL control 时的 q_norm、dq_norm、pos_err_norm、tau_norm、wheel_vel
   - JointPD 时的 q_err_norm、gravity

## 6. 试过但已撤回或不应继续盲试的方案

下面这些方向都试过，效果不稳定或导致更差现象，不建议继续盲目改：

1. 直接从 idle 进入 RL，不经过 joint_pd。
2. 把 `default_joint_angles` 改成 0。
3. 把 `home qpos` 里的关节角改成 0。
4. 修改 `home` 高度，例如改到 `z=0.363`。
5. 强制在 MuJoCo 初始化时 `mj_resetDataKeyframe`。
6. 反复试关节符号、ref、home 的组合。

目前已经按用户要求回退到“怀疑是不是介入控制太晚”的那个调试阶段。

## 7. 当前现象

机器人仍然不稳定，典型现象是前栽：

```text
头朝下、屁股朝上
不会完全翻 180 度躺下，但无法站稳
```

用户观察到：

```text
栽倒过程中 control 数据变化不大
等机器狗躺地上或姿态很差后，control 数据才在短时间有较大变化，然后停止变化
```

典型日志中出现过：

```text
FSMState_RL enter gravity=(0.66, 0, -0.74)
q_norm=8.x
default_q_norm=3.50999
q_err_norm_no_wheel=3.3
command=(0 0 0)
```

也出现过 joint_pd 后再进入 RL 时：

```text
FSMState_RL enter gravity=(0.98, 0, -0.15)
q_err_norm_no_wheel=0.49
```

这说明有时 joint_pd 把关节误差拉小了，但机身姿态已经很差。也就是说，不能只看 `q_err_norm`，还必须看 base 姿态和 MuJoCo qpos / controller joint state 是否一致。

## 8. 当前最可能的问题

1. MuJoCo joint 顺序和 controller 关节顺序不一致。
2. MuJoCo qpos、joint `ref`、`home qpos`、controller `default_joint_angles` 之间重复叠加或含义不一致。
3. controller 读取到的 q 是相对 ref，还是绝对 joint position，目前没有完全确认。
4. 训练侧关节顺序和 MuJoCo/ROS2 控制侧关节顺序不一致。
5. `reindex / obs_reindex / action_reindex / re_sign` 还没有根据实测逐项确定。
6. joint_pd 预站立阶段可能在关节误差减小的同时把机身推到错误姿态。


## 9. 推荐测试命令

Docker 内：

```bash
cd /mnt/dev
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select titatit_description mujoco_sim_ros2 rl_controller
source install/setup.bash
ros2 launch rl_controller sim_mujoco.launch.py robot:=titatit headless:=false startup_pause_sec:=8.0
```

如果只想看当前默认启动：

```bash
ros2 launch rl_controller sim_mujoco.launch.py robot:=titatit
```

## 10. 新对话继续时的建议说明

可以把这句话发给新模型：

```text
请不要继续盲目修改 home qpos、joint ref、高度或默认角。先添加精确诊断日志，逐项打印 16 个关节在 MuJoCo qpos、ROS2 controller state、joint_pd target、RL default_joint_angles 中的顺序和值，确认训练侧和 MuJoCo 控制侧的一致性后再修改。
```