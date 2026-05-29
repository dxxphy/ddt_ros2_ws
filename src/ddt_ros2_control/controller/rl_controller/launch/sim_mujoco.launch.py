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
    controller_manager_timeout_sec = "40"
    controller_service_call_timeout_sec = "10"

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
            "--controller-manager-timeout",
            controller_manager_timeout_sec,
            "--service-call-timeout",
            controller_service_call_timeout_sec,
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
            "--controller-manager-timeout",
            controller_manager_timeout_sec,
            "--service-call-timeout",
            controller_service_call_timeout_sec,
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
            "--controller-manager-timeout",
            controller_manager_timeout_sec,
            "--service-call-timeout",
            controller_service_call_timeout_sec,
            "--switch-timeout",
            "20",
        ],
    )
    topic_prefix = "/" + ns.strip("/") if ns.strip("/") else ""
    cmd_key_topic = topic_prefix + "/command/cmd_key"
    cmd_twist_topic = topic_prefix + "/command/cmd_twist"

    autostart_actions = []
    if autostart:
        rl_delay_sec = max(0.5, startup_pause_sec + rl_warmup_sec + 0.5)
        autostart_actions.append(
            ExecuteProcess(
                cmd=[
                    "python3",
                    "-c",
                    r"""
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


def wait_for_subscribers(node, publisher, topic_name, timeout_sec):
    deadline = time.monotonic() + timeout_sec
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if publisher.get_subscription_count() > 0:
            return True
    node.get_logger().warn(
        "Timed out waiting for a subscriber on {}".format(topic_name)
    )
    return False


def publish_for(node, publisher, msg, topic_name, duration_sec, rate_hz):
    wait_for_subscribers(node, publisher, topic_name, 10.0)
    period = 1.0 / rate_hz
    deadline = time.monotonic() + duration_sec
    while rclpy.ok() and time.monotonic() < deadline:
        publisher.publish(msg)
        rclpy.spin_once(node, timeout_sec=0.01)
        time.sleep(period)


cmd_key_topic = sys.argv[1]
cmd_twist_topic = sys.argv[2]
cmd_vel_x = float(sys.argv[3])
rl_delay_sec = float(sys.argv[4])

rclpy.init()
node = rclpy.create_node("titatit_mujoco_autostart")

key_qos = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)
twist_qos = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)
key_pub = node.create_publisher(String, cmd_key_topic, key_qos)
twist_pub = node.create_publisher(Twist, cmd_twist_topic, twist_qos)

joint_pd_msg = String()
joint_pd_msg.data = "joint_pd"
node.get_logger().info("Publishing joint_pd")
publish_for(node, key_pub, joint_pd_msg, cmd_key_topic, 0.8, 10.0)

deadline = time.monotonic() + rl_delay_sec
while rclpy.ok() and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.05)
    time.sleep(0.05)

if abs(cmd_vel_x) > 1e-9:
    twist_msg = Twist()
    twist_msg.linear.x = cmd_vel_x
    node.get_logger().info("Publishing cmd_vel x={:.3f}".format(cmd_vel_x))
    publish_for(node, twist_pub, twist_msg, cmd_twist_topic, 2.0, 20.0)

rl_msg = String()
rl_msg.data = "rl_0"
node.get_logger().info("Publishing rl_0")
publish_for(node, key_pub, rl_msg, cmd_key_topic, 1.0, 10.0)

time.sleep(0.5)
node.destroy_node()
rclpy.shutdown()
""",
                    cmd_key_topic,
                    cmd_twist_topic,
                    str(cmd_vel_x),
                    str(rl_delay_sec),
                ],
                output="screen",
            )
        )

    def on_spawner_success(spawner_name, actions):
        def _on_exit(event, context):
            if event.returncode == 0:
                return actions
            return [
                launch.actions.LogInfo(
                    msg=(
                        spawner_name
                        + " spawner exited with code "
                        + str(event.returncode)
                        + "; dependent startup actions were skipped"
                    )
                )
            ]

        return _on_exit

    return [
        mujoco_simulate_app,
        robot_state_publisher,
        RegisterEventHandler(
            event_handler=OnProcessStart(
                target_action=mujoco_simulate_app,
                on_start=[
                    joint_state_broadcaster_spawner,
                    rl_controller_spawner,
                ],
            )
        ),
        RegisterEventHandler(
            event_handler=OnProcessExit(
                target_action=rl_controller_spawner,
                on_exit=on_spawner_success(
                    robot_name + "_rl_controller",
                    [imu_sensor_broadcaster_spawner] + autostart_actions,
                ),
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
            default_value="8.0",
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
            default_value="3.0",
            description="Optional extra time to hold joint_pd before publishing cmd_vel and switching to rl_0",
        )
    )
    return LaunchDescription(
        declared_arguments + [OpaqueFunction(function=launch_setup)]
    )
