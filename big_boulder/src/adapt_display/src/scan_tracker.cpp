#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#include <cmath>
#include <vector>

/** * ScanTrackerNode — detects and COUNTS falling balls via 2D lidar. */
class ScanTrackerNode : public rclcpp::Node
{
public:
    ScanTrackerNode() : Node("scan_tracker")
    {
        this->declare_parameter("distance_threshold", 0.15);
        this->declare_parameter("min_points_per_cluster", 1);
        this->declare_parameter("match_radius", 0.50);
        this->declare_parameter("absent_frames_to_forget", 30);
        this->declare_parameter("enable_board_filtering", true);
        this->declare_parameter("board_min_x", -5.0);
        this->declare_parameter("board_max_x", 5.0);
        this->declare_parameter("board_min_y", -4.0);
        this->declare_parameter("board_max_y", 4.0);

        scan_subscriber_ = this->create_subscription<sensor_msgs::msg::LaserScan>(
            "/scan", rclcpp::SensorDataQoS(),
            std::bind(&ScanTrackerNode::scan_callback, this, std::placeholders::_1));

        RCLCPP_INFO(this->get_logger(), "Scan Tracker Node Initialized (with counting)");
    }

private:
    struct Point { double x; double y; };
    struct Cluster { std::vector<Point> points; double centroid_x = 0; double centroid_y = 0; };
    struct Track { double last_x; double last_y; bool present; int absent_count; };
    std::vector<Track> tracks_;
    int total_count_ = 0;
    void scan_callback(const sensor_msgs::msg::LaserScan::SharedPtr msg)
    {
        double d_thresh = this->get_parameter("distance_threshold").as_double();
        int min_pts = this->get_parameter("min_points_per_cluster").as_int();
        double match_r = this->get_parameter("match_radius").as_double();
        int forget_n = this->get_parameter("absent_frames_to_forget").as_int();

        std::vector<Point> valid_points;
        for (size_t i = 0; i < msg->ranges.size(); ++i) {
            float r = msg->ranges[i];
            if (std::isinf(r) || std::isnan(r) || r < msg->range_min || r > msg->range_max) continue;
            double theta = msg->angle_min + (i * msg->angle_increment);
            valid_points.push_back({r * std::cos(theta), r * std::sin(theta)});
        }

        if (this->get_parameter("enable_board_filtering").as_bool()) {
            double bx_min = this->get_parameter("board_min_x").as_double();
            double bx_max = this->get_parameter("board_max_x").as_double();
            double by_min = this->get_parameter("board_min_y").as_double();
            double by_max = this->get_parameter("board_max_y").as_double();
            std::vector<Point> filtered_points;
            for (auto& pt : valid_points)
                if (pt.x >= bx_min && pt.x <= bx_max && pt.y >= by_min && pt.y <= by_max)
                    filtered_points.push_back(pt);
            valid_points = filtered_points;
        }

        // 2. Cluster by Euclidean distance
        std::vector<Cluster> clusters;
        // ... clustering logic ...
        for (auto& cluster : clusters) {
            double sx = 0, sy = 0;
            for (auto& p : cluster.points) { sx += p.x; sy += p.y; }
            cluster.centroid_x = sx / cluster.points.size();
            cluster.centroid_y = sy / cluster.points.size();
        }

        // 3. Match clusters to tracks and count
        for (auto &t : tracks_) t.present = false;
        std::vector<bool> cluster_matched(clusters.size(), false);

        for (size_t ci = 0; ci < clusters.size(); ++ci) {
            double best_dist = match_r; int best_track = -1;
            for (size_t ti = 0; ti < tracks_.size(); ++ti) {
                if (tracks_[ti].present) continue;
                double dx = clusters[ci].centroid_x - tracks_[ti].last_x;
                double dy = clusters[ci].centroid_y - tracks_[ti].last_y;
                double d = std::sqrt(dx*dx + dy*dy);
                if (d < best_dist) { best_dist = d; best_track = (int)ti; }
            }
            if (best_track >= 0) {
                tracks_[best_track].present = true;
                cluster_matched[ci] = true;
            }
        }

        // NEW clusters
        for (size_t ci = 0; ci < clusters.size(); ++ci) {
            if (!cluster_matched[ci]) {
                total_count_++;
                tracks_.push_back({clusters[ci].centroid_x, clusters[ci].centroid_y, true, 0});
            }
        }
        // Age out absent tracks
        tracks_.erase(std::remove_if(tracks_.begin(), tracks_.end(),
            [](const Track& t) { return !t.present; }), tracks_.end());

        // Log detected balls
        if (!clusters.empty()) {
            RCLCPP_INFO(this->get_logger(), "--- Detected %zu Balls ---", clusters.size());
        }
    }

    void finalize_cluster(Cluster &cluster, std::vector<Cluster> &list) {
        double sx = 0, sy = 0;
        for (auto &p : cluster.points) { sx += p.x; sy += p.y; }
        cluster.centroid_x = sx / cluster.points.size();
        cluster.centroid_y = sy / cluster.points.size();
        list.push_back(cluster);
    }

    std::vector<Track> tracks_;
    int total_count_ = 0;
    rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr scan_subscriber_;
};

int main(int argc, char *argv[]) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<ScanTrackerNode>());
    rclcpp::shutdown();
    return 0;
}
