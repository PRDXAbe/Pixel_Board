#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

class PyNode(Node):
    def __init__(self):
        super().__init__('py_node')
        self.get_logger().info('Hello from Python')

def main(args=None):
    rclpy.init(args=args)
    node = PyNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()
