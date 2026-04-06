#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#include <std_msgs/msg/int32.hpp>
#include <std_msgs/msg/float32_multi_array.hpp>
#include <cmath>
#include <vector>
#include <algorithm>

/**
 * ScanTrackerNode — detects and counts balls via 2D LIDAR.
 *
 * Publishes:
 *   /ball_count     std_msgs/Int32             — running total
 *   /ball_positions std_msgs/Float32MultiArray — flat [x1,y1, x2,y2, ...]
 */
class ScanTrackerNode : public rclcpp::Node
{
public:
    ScanTrackerNode() : Node("scan_tracker")
    {
        this->declare_parameter("distance_threshold",      0.10);
        this->declare_parameter("min_points_per_cluster",  1);
        this->declare_parameter("match_radius",            0.50);
        this->declare_parameter("absent_frames_to_forget", 30);
        this->declare_parameter("enable_board_filtering",  true);
        this->declare_parameter("board_min_x", -5.0);
        this->declare_parameter("board_max_x",  5.0);
        this->declare_parameter("board_min_y", -4.0);
        this->declare_parameter("board_max_y",  4.0);

        scan_subscriber_ = this->create_subscription<sensor_msgs::msg::LaserScan>(
            "/scan", rclcpp::SensorDataQoS(),
            std::bind(&ScanTrackerNode::scan_callback, this, std::placeholders::_1));

        count_publisher_ = this->create_publisher<std_msgs::msg::Int32>("/ball_count", 10);
        positions_publisher_ = this->create_publisher<std_msgs::msg::Float32MultiArray>("/ball_positions", 10);

        RCLCPP_INFO(this->get_logger(), "Scan Tracker Node Initialized (with counting)");
    }

private:
    struct Point   { double x; double y; };
    struct Cluster { std::vector<Point> points; double centroid_x = 0; double centroid_y = 0; };
    struct Track   { double last_x; double last_y; bool present; int absent_count; };

    std::vector<Track> tracks_;
    int total_count_ = 0;

    rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr          scan_subscriber_;
    rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr                    count_publisher_;
    rclcpp::Publisher<std_msgs::msg::Float32MultiArray>::SharedPtr        positions_publisher_;

    void finalize_cluster(Cluster &cluster, std::vector<Cluster> &list) {
        double sx = 0, sy = 0;
        for (auto &p : cluster.points) { sx += p.x; sy += p.y; }
        cluster.centroid_x = sx / cluster.points.size();
        cluster.centroid_y = sy / cluster.points.size();
        list.push_back(cluster);
    }

    void scan_callback(const sensor_msgs::msg::LaserScan::SharedPtr msg)
    {
        double d_thresh = this->get_parameter("distance_threshold").as_double();
        int    min_pts  = this->get_parameter("min_points_per_cluster").as_int();
        double match_r  = this->get_parameter("match_radius").as_double();
        int    forget_n = this->get_parameter("absent_frames_to_forget").as_int();

        // 1. Convert polar → Cartesian, drop invalid readings
        std::vector<Point> valid_points;
        for (size_t i = 0; i < msg->ranges.size(); ++i) {
            float r = msg->ranges[i];
            if (std::isinf(r) || std::isnan(r) || r < msg->range_min || r > msg->range_max) continue;
            double theta = msg->angle_min + (i * msg->angle_increment);
            valid_points.push_back({r * std::cos(theta), r * std::sin(theta)});
        }

        // 2. Board filtering — discard points outside the board rectangle
        if (this->get_parameter("enable_board_filtering").as_bool()) {
            double bx_min = this->get_parameter("board_min_x").as_double();
            double bx_max = this->get_parameter("board_max_x").as_double();
            double by_min = this->get_parameter("board_min_y").as_double();
            double by_max = this->get_parameter("board_max_y").as_double();
            std::vector<Point> filtered;
            for (auto &pt : valid_points)
                if (pt.x >= bx_min && pt.x <= bx_max && pt.y >= by_min && pt.y <= by_max)
                    filtered.push_back(pt);
            valid_points = filtered;
        }

        // 3. Cluster by Euclidean distance (simple single-pass)
        std::vector<Cluster> clusters;
        for (auto &pt : valid_points) {
            bool added = false;
            for (auto &cl : clusters) {
                double dx = pt.x - cl.centroid_x;
                double dy = pt.y - cl.centroid_y;
                if (std::sqrt(dx*dx + dy*dy) < d_thresh) {
                    cl.points.push_back(pt);
                    // Update running centroid
                    double sx = 0, sy = 0;
                    for (auto &p : cl.points) { sx += p.x; sy += p.y; }
                    cl.centroid_x = sx / cl.points.size();
                    cl.centroid_y = sy / cl.points.size();
                    added = true;
                    break;
                }
            }
            if (!added) {
                Cluster nc;
                nc.points.push_back(pt);
                nc.centroid_x = pt.x;
                nc.centroid_y = pt.y;
                clusters.push_back(nc);
            }
        }

        // Drop clusters that are too small
        clusters.erase(std::remove_if(clusters.begin(), clusters.end(),
            [min_pts](const Cluster &c) { return (int)c.points.size() < min_pts; }),
            clusters.end());

        // 4. Match clusters to existing tracks
        for (auto &t : tracks_) t.present = false;
        std::vector<bool> cluster_matched(clusters.size(), false);

        for (size_t ci = 0; ci < clusters.size(); ++ci) {
            double best_dist = match_r; int best_track = -1;
            for (size_t ti = 0; ti < tracks_.size(); ++ti) {
                if (tracks_[ti].present) continue;
                double dx = clusters[ci].centroid_x - tracks_[ti].last_x;
                double dy = clusters[ci].centroid_y - tracks_[ti].last_y;
                double d  = std::sqrt(dx*dx + dy*dy);
                if (d < best_dist) { best_dist = d; best_track = (int)ti; }
            }
            if (best_track >= 0) {
                tracks_[best_track].last_x   = clusters[ci].centroid_x;
                tracks_[best_track].last_y   = clusters[ci].centroid_y;
                tracks_[best_track].present  = true;
                tracks_[best_track].absent_count = 0;
                cluster_matched[ci] = true;
            }
        }

        // 5. New cluster → new ball → increment counter
        for (size_t ci = 0; ci < clusters.size(); ++ci) {
            if (!cluster_matched[ci]) {
                total_count_++;
                tracks_.push_back({clusters[ci].centroid_x, clusters[ci].centroid_y, true, 0});
                RCLCPP_INFO(this->get_logger(), "New ball detected! Total: %d", total_count_);
            }
        }

        // 6. Age out absent tracks
        for (auto &t : tracks_) {
            if (!t.present) t.absent_count++;
        }
        tracks_.erase(std::remove_if(tracks_.begin(), tracks_.end(),
            [forget_n](const Track &t) { return t.absent_count >= forget_n; }),
            tracks_.end());

        // 7. Publish /ball_count
        std_msgs::msg::Int32 count_msg;
        count_msg.data = total_count_;
        count_publisher_->publish(count_msg);

        // 8. Publish /ball_positions (flat [x1,y1, x2,y2, ...] of current visible clusters)
        std_msgs::msg::Float32MultiArray pos_msg;
        pos_msg.data.reserve(clusters.size() * 2);
        for (const auto &c : clusters) {
            pos_msg.data.push_back(static_cast<float>(c.centroid_x));
            pos_msg.data.push_back(static_cast<float>(c.centroid_y));
        }
        positions_publisher_->publish(pos_msg);

        if (!clusters.empty()) {
            RCLCPP_INFO(this->get_logger(), "--- Detected %zu ball(s) on board ---", clusters.size());
        }
    }
};

int main(int argc, char *argv[]) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<ScanTrackerNode>());
    rclcpp::shutdown();
    return 0;
}
