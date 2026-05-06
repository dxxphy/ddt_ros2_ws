import launch
import os
import xacro

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, OpaqueFunction, RegisterEventHandler, TimerAction
from launch.event_handlers import OnProcessStart, OnProcessExit
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_setup(context, *args, **kwargs):
    robot_name = LaunchConfiguration("robot").perform(context)
    ns = LaunchConfiguration("ns").perform(context)
    headless = LaunchConfiguration("headless").perform(context).lower() in (
        "1",
        "true",
        "yes",
    )
    autostart = LaunchConfiguration("autostart").perform(context).lower() in (
        "1",
        "true",
        "yes",
    )
    startup_pause_sec = float(LaunchConfiguration("startup_pause_sec").perform(context))
    cmd_vel_x = float(LaunchConfiguration("cmd_vel_x").perform(context))
    rl_warmup_sec = float(LaunchConfiguration("rl_warmup_sec").perform(context))
    robot_xacro_path = os.path.join(
        get_package_share_directory(robot_name + "_description"),
        "xacro",
        "robot.xacro",
    )
    robot_description = xacro.process_file(
        robot_xacro_path, mappings={"hw_env": "mujoco"}
    ).toxml()

    robot_controllers = os.path.join(
        get_package_share_directory("rl_controller"),
        "config",
        robot_name,
        "controllers.yaml",
    )

    mujoco_simulate_app = Node(
        package='mujoco_sim_ros2',
        executable='mujoco_sim',
        namespace=ns,
        parameters=[
            {"model_package": robot_name + "_description"},
            {"model_file": "mujoco/scene.xml"},
            {"physics_plugins": ["mujoco_ros2_control::MujocoRos2ControlPlugin"]},
            {"robot_description": robot_description},
            {"headless": headless},
            {"startup_pause_sec": startup_pause_sec},
            robot_controllers
        ],
        output='screen'
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        namespace=ns,
        parameters=[
            {"robot_description": robot_description},
            {"use_sim_time": True},
        ],
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            ns + "/controller_manager",
            "--switch-timeout",
            "20",
        ],
    )
    imu_sensor_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "imu_sensor_broadcaster",
            "--controller-manager",
            ns + "/controller_manager",
            "--switch-timeout",
            "20",
        ],
    )

    rl_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            robot_name + "_rl_controller",
            "--controller-manager",
            ns + "/controller_manager",
            "--switch-timeout",
            "20",
        ],
    )
    topic_prefix = "/" + ns.strip("/") if ns.strip("/") else ""
    cmd_key_topic = topic_prefix + "/command/cmd_key"
    cmd_twist_topic = topic_prefix + "/command/cmd_twist"
    autostart_actions = []
    if autostart:
        joint_pd_action = ExecuteProcess(
            cmd=[
                "ros2", "topic", "pub", "--once", cmd_key_topic,
                "std_msgs/msg/String", "{data: joint_pd}",
            ],
            output="screen",
        )
        # Publish joint_pd as soon as the controller is active.  MuJoCo may
        # still be in startup_pause_sec, but the subscription callback is spun
        # by the controller-manager executor; the first physics/control update
        # will then enter joint_pd instead of spending live physics time in idle.
        autostart_actions.append(TimerAction(period=0.2, actions=[joint_pd_action]))

        delayed_rl_actions = []
        if abs(cmd_vel_x) > 1e-9:
            delayed_rl_actions.append(
                ExecuteProcess(
                    cmd=[
                        "ros2", "topic", "pub", "--once", cmd_twist_topic,
                        "geometry_msgs/msg/Twist",
                        "{linear: {x: " + str(cmd_vel_x) + ", y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}",
                    ],
                    output="screen",
                )
            )
        rl_start_action = ExecuteProcess(
            cmd=[
                "ros2", "topic", "pub", "--once", cmd_key_topic,
                "std_msgs/msg/String", "{data: rl_0}",
            ],
            output="screen",
        )
        delayed_rl_actions.append(TimerAction(period=0.2, actions=[rl_start_action]))
        rl_delay_sec = max(0.5, startup_pause_sec + rl_warmup_sec + 0.5)
        autostart_actions.append(TimerAction(period=rl_delay_sec, actions=delayed_rl_actions))
    return [
        mujoco_simulate_app,
        robot_state_publisher,
        RegisterEventHandler(
            event_handler=OnProcessStart(
                target_action=mujoco_simulate_app,
                on_start=[
                    TimerAction(
                        period=2.0,
                        actions=[
                            joint_state_broadcaster_spawner,
                            rl_controller_spawner,
                        ],
                    )
                ],
            )
        ),
        RegisterEventHandler(
            event_handler=OnProcessExit(
                target_action=rl_controller_spawner,
                on_exit=[imu_sensor_broadcaster_spawner],
            )
        ),
        RegisterEventHandler(
            event_handler=OnProcessExit(
                target_action=rl_controller_spawner,
                on_exit=autostart_actions,
            )
        ),
    ]
    

def generate_launch_description():
    declared_arguments = []
    declared_arguments.append(
        launch.actions.DeclareLaunchArgument(
            "robot",
            default_value="titatit",
            description="Path to the robot description file",
        )
    )
    declared_arguments.append(
        launch.actions.DeclareLaunchArgument(
            "ns",
            default_value="",
            description="Namespace of launch",
        )
    )
    declared_arguments.append(
        launch.actions.DeclareLaunchArgument(
            "headless",
            default_value="false",
            description="Run MuJoCo without the GLFW viewer",
        )
    )
    declared_arguments.append(
        launch.actions.DeclareLaunchArgument(
            "startup_pause_sec",
            default_value="3.0",
            description="Delay physics stepping after ros2_control is created, giving spawners time to activate controllers",
        )
    )
    declared_arguments.append(
        launch.actions.DeclareLaunchArgument(
            "autostart",
            default_value="true",
            description="Automatically switch to the first RL policy after the RL controller is active",
        )
    )
    declared_arguments.append(
        launch.actions.DeclareLaunchArgument(
            "cmd_vel_x",
            default_value="1.0",
            description="Optional forward velocity command to publish before autostarting the policy",
        )
    )
    declared_arguments.append(
        launch.actions.DeclareLaunchArgument(
            "rl_warmup_sec",
            default_value="1.0",
            description="Optional extra time to hold joint_pd before publishing cmd_vel and switching to rl_0",
        )
    )
    return LaunchDescription(
        declared_arguments + [OpaqueFunction(function=launch_setup)]
    )
