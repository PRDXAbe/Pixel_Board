from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='adapt_display',
            executable='cpp_node',
            name='cpp_node',
            output='screen'
        ),
        Node(
            package='adapt_display',
            executable='py_node.py',
            name='py_node',
            output='screen'
        )
    ])
