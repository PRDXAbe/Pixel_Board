cmake_minimum_required(VERSION 3.8)
project(adapt_display)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclpy REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

# Install Python modules
ament_python_install_package(${PROJECT_NAME})

# Install Python scripts
install(PROGRAMS
  scripts/py_node.py
  scripts/spawn_single_ball.py
  scripts/spawn_multiple_balls.py
  scripts/remove_balls.py
  scripts/rw_viz.py
  DESTINATION lib/${PROJECT_NAME}
)

# C++ Node
add_executable(cpp_node src/cpp_node.cpp)
target_include_directories(cpp_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(cpp_node PUBLIC cxx_std_17)
ament_target_dependencies(cpp_node rclcpp)

install(TARGETS cpp_node
  DESTINATION lib/${PROJECT_NAME})

# Scan Tracker Node
add_executable(scan_tracker src/scan_tracker.cpp)
target_include_directories(scan_tracker PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(scan_tracker PUBLIC cxx_std_17)
ament_target_dependencies(scan_tracker rclcpp sensor_msgs std_msgs)

install(TARGETS scan_tracker
  DESTINATION lib/${PROJECT_NAME})

# Install all resource directories (launch, config, description, etc.)
# Any new top-level directory (e.g. meshes, worlds, rviz, maps) will
# automatically be installed without needing to modify this file.
install(DIRECTORY
  launch
  config
  description
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
