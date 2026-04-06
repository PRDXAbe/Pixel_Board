cd /home/abhinav/Projects/big_boulder                                                                                                                                                                    
  source /opt/ros/humble/setup.bash    
  source install/setup.bash                                                                                                                                                                                
                                                                                                                                                                                                           
  ros2 run adapt_display spawn_single_ball.py --ros-args \                                                                                                                                                 
   -p use_exact_position:=true \                                                                                                                                                                           
   -p exact_x:=0.0 \                                                                                                                                                                                       
   -p exact_y:=0.0 \                                                                                                                                                                                       
   -p spawn_height:=2.0 \                                                                                                                                                                                  
   -p board_min_x:=-1.5 \                                                                                                                                                                                  
   -p board_max_x:=1.5 \                                                                                                                                                                                   
   -p board_min_y:=-1.2 \                                                                                                                                                                                  
   -p board_max_y:=1.2
