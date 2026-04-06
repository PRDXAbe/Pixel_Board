#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from gazebo_msgs.srv import GetModelList, DeleteEntity

class RemoveBallsNode(Node):
    def __init__(self):
        super().__init__('remove_balls')
        self.declare_parameter('num_balls', -1)
        
        self.get_model_list_client = self.create_client(GetModelList, '/get_model_list')
        self.delete_entity_client = self.create_client(DeleteEntity, '/delete_entity')
        
        while not self.get_model_list_client.wait_for_service(timeout_sec=1.0) or \
              not self.delete_entity_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Services not available, waiting again...')
            
        self.remove_balls()
        
    def remove_balls(self):
        num_balls = self.get_parameter('num_balls').value
        
        # Get list of all models
        request = GetModelList.Request()
        future = self.get_model_list_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        
        if future.result() is not None:
            models = future.result().model_names
        else:
            self.get_logger().error("Failed to get model list")
            return
            
        # Filter for balls
        ball_models = [m for m in models if m.startswith('ball_')]
        
        if not ball_models:
            self.get_logger().info("No balls found in the simulation to remove.")
            return
            
        self.get_logger().info(f"Found {len(ball_models)} balls in the simulation.")
        
        # Determine which to remove
        if num_balls > 0 and num_balls < len(ball_models):
            # We assume the order they appear in GetModelList or their lexical
            # order is the order of spawning. Since they're assigned random UUIDs,
            # we rely on Gazebo's model list iteration order which generally appends
            # newer items to the end.
            balls_to_remove = ball_models[-num_balls:]
        else:
            balls_to_remove = ball_models
            
        self.get_logger().info(f"Removing {len(balls_to_remove)} balls...")
        
        for ball_name in balls_to_remove:
            req = DeleteEntity.Request()
            req.name = ball_name
            del_future = self.delete_entity_client.call_async(req)
            rclpy.spin_until_future_complete(self, del_future)
            
            if del_future.result() and del_future.result().success:
                self.get_logger().info(f"Successfully deleted {ball_name}")
            else:
                self.get_logger().error(f"Failed to delete {ball_name}")

def main(args=None):
    rclpy.init(args=args)
    node = RemoveBallsNode()
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
