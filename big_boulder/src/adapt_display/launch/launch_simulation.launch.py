import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.substitutions import LaunchConfiguration, Command
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    # Check if we're told to use sim time
    use_sim_time = LaunchConfiguration('use_sim_time')

    # Get package path
    pkg_path = os.path.join(get_package_share_directory('adapt_display'))

    # Separate URDF files for each component
    lidar_xacro = os.path.join(pkg_path, 'description/lidar_platform.urdf.xacro')
    board_xacro = os.path.join(pkg_path, 'description/drawing_board.urdf.xacro')

    gazebo_params_file = os.path.join(pkg_path, 'config/gazebo_params.yaml')

    # Launch gazebo simulation
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([os.path.join(
            get_package_share_directory('gazebo_ros'), "launch", 'gazebo.launch.py')]),
        launch_arguments={'extra_gazebo_args': '--ros-args --params-file ' + gazebo_params_file}.items()
    )

    # Robot description configs for both models (with namespaces)
    lidar_description_config = Command(['xacro ', lidar_xacro])
    board_description_config = Command(['xacro ', board_xacro])

    # Separate parameters for each model
    lidar_params = {
        'robot_description': ParameterValue(lidar_description_config, value_type=str),
        'use_sim_time': use_sim_time
    }
    board_params = {
        'robot_description': ParameterValue(board_description_config, value_type=str),
        'use_sim_time': use_sim_time
    }

    # Robot state publishers for each model.
    # namespace= is critical: it causes robot_state_publisher to publish
    # /lidar_platform/robot_description and /drawing_board/robot_description —
    # exactly the topics that spawn_entity.py -topic argument looks for.
    node_lidar_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace='lidar_platform',
        output='screen',
        parameters=[lidar_params],
    )

    node_board_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace='drawing_board',
        output='screen',
        parameters=[board_params],
    )

    # LIDAR platform: top-centre edge of the board, elevated on its support.
    # Board top edge is at world Y=0; LIDAR is at Y=+0.2 (just beyond the edge)
    # so it hangs over the board.  Height 1.5m: balls spawn at 2m and fall
    # through the 1.5m horizontal scan plane before reaching the board surface.
    # Yaw -1.5708 (-π/2): rotates sensor local +X to face world -Y (into board)
    # so the 180° scan fan covers the board from left to right in the top-down view.
    spawn_lidar = Node(package='gazebo_ros', executable='spawn_entity.py',
                       arguments=['-topic', '/lidar_platform/robot_description',
                                  '-entity', 'lidar_platform',
                                  '-x', '0.0',
                                  '-y', '0.2',
                                  '-z', '1.5',
                                  '-Y', '-1.5708'],
                       output='screen')

    # Spawn drawing board after a 4s delay — Gazebo needs time to initialise
    # the /spawn_entity service before handling a second simultaneous spawn.
    # Without the delay both spawn_entity processes race and gzserver crashes (exit 255).
    spawn_board_delayed = TimerAction(
        period=4.0,
        actions=[
            Node(package='gazebo_ros', executable='spawn_entity.py',
                 arguments=['-topic', '/drawing_board/robot_description',
                             '-entity', 'drawing_board',
                             '-x', '0.0',
                             '-y', '-1.2',
                             '-z', '0.8'],
                 output='screen')
        ]
    )

    # Launch!
    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use sim time if true'),
        DeclareLaunchArgument(
            'use_ros2_control',
            default_value='true',
            description='Use ros2_control if true'),

        node_lidar_state_publisher,
        node_board_state_publisher,
        gazebo,
        spawn_lidar,
        spawn_board_delayed
    ])
