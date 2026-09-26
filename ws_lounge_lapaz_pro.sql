-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Sep 22, 2026 at 04:18 AM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `ws_lounge_lapaz_pro`
--

-- --------------------------------------------------------

--
-- Table structure for table `addons`
--

CREATE TABLE `addons` (
  `id` int(11) NOT NULL,
  `name` varchar(128) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `unit_price` float NOT NULL,
  `requires_quantity` tinyint(1) DEFAULT NULL,
  `min_quantity` int(11) DEFAULT NULL,
  `max_quantity` int(11) DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `attendance_logs`
--

CREATE TABLE `attendance_logs` (
  `id` int(11) NOT NULL,
  `membership_id` int(11) NOT NULL,
  `check_in_time` datetime NOT NULL,
  `check_out_time` datetime DEFAULT NULL,
  `hours_deducted` float DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `is_paused` tinyint(1) DEFAULT 0,
  `paused_at` datetime DEFAULT NULL,
  `accumulated_paused_seconds` int(11) DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `attendance_logs`
--

INSERT INTO `attendance_logs` (`id`, `membership_id`, `check_in_time`, `check_out_time`, `hours_deducted`, `created_at`, `is_paused`, `paused_at`, `accumulated_paused_seconds`) VALUES
(26, 4, '2026-09-22 10:07:21', '2026-09-22 10:14:25', 0.08, '2026-09-22 10:07:21', 0, NULL, 123),
(27, 4, '2026-09-22 10:15:18', '2026-09-22 10:15:29', 0, '2026-09-22 10:15:18', 0, NULL, 0);

-- --------------------------------------------------------

--
-- Table structure for table `daily_reports`
--

CREATE TABLE `daily_reports` (
  `id` int(11) NOT NULL,
  `report_date` date DEFAULT NULL,
  `total_check_ins` int(11) DEFAULT NULL,
  `total_logins` int(11) DEFAULT NULL,
  `total_timelogged` float DEFAULT NULL,
  `generated_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `daily_reports`
--

INSERT INTO `daily_reports` (`id`, `report_date`, `total_check_ins`, `total_logins`, `total_timelogged`, `generated_at`) VALUES
(3, '2026-09-22', 2, 0, 310, '2026-09-22 10:14:08');

-- --------------------------------------------------------

--
-- Table structure for table `equipment`
--

CREATE TABLE `equipment` (
  `id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `type` varchar(50) DEFAULT NULL,
  `hourly_rate` decimal(10,2) DEFAULT 0.00,
  `quantity_available` int(11) DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `equipment`
--

INSERT INTO `equipment` (`id`, `name`, `type`, `hourly_rate`, `quantity_available`) VALUES
(1, 'Projector', 'projector', 100.00, 2),
(2, 'Extra Chair', 'extra chair', 0.00, 2),
(3, 'Extension Cord', 'extension cord', 0.00, 1),
(4, 'Microphone', 'mic', 0.00, 2),
(5, 'Speaker', 'speaker', 0.00, 2);

-- --------------------------------------------------------

--
-- Table structure for table `inventory`
--

CREATE TABLE `inventory` (
  `id` int(11) NOT NULL,
  `item_name` varchar(100) NOT NULL,
  `category` varchar(50) DEFAULT NULL,
  `quantity` int(11) DEFAULT 0,
  `price` decimal(10,2) DEFAULT 0.00
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `memberships`
--

CREATE TABLE `memberships` (
  `id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `status` varchar(20) DEFAULT NULL,
  `start_date` datetime DEFAULT NULL,
  `expiry_date` datetime NOT NULL,
  `total_hours` float DEFAULT NULL,
  `hours_left` float DEFAULT NULL,
  `plan_name` varchar(100) DEFAULT NULL,
  `is_checked_in` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `is_checked_out` tinyint(1) DEFAULT 0,
  `is_paused` tinyint(1) DEFAULT 0,
  `paused_at` datetime DEFAULT NULL,
  `accumulated_paused_seconds` int(11) DEFAULT 0,
  `member_list_notification_seen` tinyint(1) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `memberships`
--

INSERT INTO `memberships` (`id`, `user_id`, `status`, `start_date`, `expiry_date`, `total_hours`, `hours_left`, `plan_name`, `is_checked_in`, `created_at`, `updated_at`, `is_checked_out`, `is_paused`, `paused_at`, `accumulated_paused_seconds`, `member_list_notification_seen`) VALUES
(4, 102, 'active', '2026-09-22 10:15:18', '2026-09-22 14:15:18', 4, 4, 'INDIVIDUAL RATE (4HRS)', 0, '2026-09-22 10:06:46', '2026-09-22 10:15:29', 1, 0, NULL, 0, 1);

-- --------------------------------------------------------

--
-- Table structure for table `payment_info`
--

CREATE TABLE `payment_info` (
  `id` int(11) NOT NULL,
  `method` varchar(32) NOT NULL,
  `account_name` varchar(128) DEFAULT NULL,
  `account_number` varchar(64) DEFAULT NULL,
  `qr_image` varchar(255) DEFAULT NULL,
  `instructions` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `payment_info`
--

INSERT INTO `payment_info` (`id`, `method`, `account_name`, `account_number`, `qr_image`, `instructions`, `created_at`, `updated_at`) VALUES
(1, 'GCash', 'WS Students & Professionals Lounge', '0999XXXXXXX', 'gcashqr.png', 'Please make your payment using the details above and upload your payment receipt', '2026-06-07 14:52:33', '2026-07-21 14:02:33'),
(2, 'Maya', 'WS Students & Professionals Lounge', '0999XXXXXXX', 'paymayaqr.png', 'Please make your payment using the details above and upload your payment receipt', '2026-06-07 14:52:33', '2026-07-21 14:02:33');

-- --------------------------------------------------------

--
-- Table structure for table `reservations`
--

CREATE TABLE `reservations` (
  `id` int(11) NOT NULL,
  `customer_id` int(11) DEFAULT NULL,
  `user_id` int(11) DEFAULT NULL,
  `room_id` int(11) NOT NULL,
  `customer_name` varchar(64) DEFAULT NULL,
  `contact_number` varchar(20) DEFAULT NULL,
  `address` varchar(128) DEFAULT NULL,
  `pax_count` int(11) DEFAULT NULL,
  `start_time` datetime NOT NULL,
  `end_time` datetime DEFAULT NULL,
  `is_open_time` tinyint(1) DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `total_amount` float DEFAULT NULL,
  `amount_paid` float DEFAULT NULL,
  `payment_method` varchar(50) DEFAULT NULL,
  `payment_type` varchar(20) DEFAULT NULL,
  `receipt_image` varchar(255) DEFAULT NULL,
  `approved_by_id` int(11) DEFAULT NULL,
  `paid` tinyint(1) DEFAULT NULL,
  `added_by` varchar(64) DEFAULT NULL,
  `extra_notes` varchar(255) DEFAULT NULL,
  `extra_fee` float DEFAULT NULL,
  `discount_rate` float DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `addon_name` varchar(64) DEFAULT NULL,
  `addon_quantity` int(11) DEFAULT 0,
  `addon_total` float DEFAULT 0,
  `addon_subtotal` float DEFAULT 0,
  `is_paused` tinyint(1) DEFAULT 0,
  `paused_at` datetime DEFAULT NULL,
  `accumulated_paused_seconds` int(11) DEFAULT 0,
  `confirmation_notification_seen` tinyint(1) DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `reservations`
--

INSERT INTO `reservations` (`id`, `customer_id`, `user_id`, `room_id`, `customer_name`, `contact_number`, `address`, `pax_count`, `start_time`, `end_time`, `is_open_time`, `status`, `total_amount`, `amount_paid`, `payment_method`, `payment_type`, `receipt_image`, `approved_by_id`, `paid`, `added_by`, `extra_notes`, `extra_fee`, `discount_rate`, `created_at`, `addon_name`, `addon_quantity`, `addon_total`, `addon_subtotal`, `is_paused`, `paused_at`, `accumulated_paused_seconds`, `confirmation_notification_seen`) VALUES
(31, 100, 3, 5, 'junard', '09742034234', NULL, 1, '2026-09-22 09:47:57', '2026-09-22 09:47:57', 1, 'Walk-in', 250, 0, NULL, 'Downpayment', NULL, NULL, 0, 'wslounge', '', 0, 0, '2026-09-22 09:47:58', NULL, 0, 0, 0, 0, NULL, 0, 0),
(32, 1, 3, 1, 'darwen', '09742034234', NULL, 1, '2026-09-22 09:58:45', '2026-09-22 10:12:34', 1, 'Checked-Out', 10, 0, NULL, 'Downpayment', NULL, NULL, 1, 'wslounge', '', 0, 0, '2026-09-22 09:58:46', NULL, 0, 0, 0, 0, NULL, 0, 0),
(33, 101, 3, 2, 'oyo tamayo', '09742034234', NULL, 1, '2026-09-22 10:02:00', '2026-09-22 10:14:08', 0, 'Checked-Out', 300, 0, NULL, 'Downpayment', NULL, NULL, 1, 'wslounge', '', 0, 0, '2026-09-22 09:59:53', NULL, 0, 0, 0, 0, NULL, 200, 0),
(34, 102, 3, 4, 'Ramil', '09283748273', NULL, 6, '2026-09-23 06:00:00', '2026-09-23 10:00:00', 0, 'Confirmed', 800, 0, NULL, 'Downpayment', NULL, NULL, 0, 'wslounge', '', 0, 0, '2026-09-22 10:01:51', NULL, 0, 0, 0, 0, NULL, 0, 0);

-- --------------------------------------------------------

--
-- Table structure for table `reservation_addons`
--

CREATE TABLE `reservation_addons` (
  `id` int(11) NOT NULL,
  `reservation_id` int(11) NOT NULL,
  `addon_id` int(11) NOT NULL,
  `quantity` int(11) NOT NULL,
  `unit_price` float NOT NULL,
  `subtotal` float DEFAULT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `rooms`
--

CREATE TABLE `rooms` (
  `id` int(11) NOT NULL,
  `name` varchar(64) NOT NULL,
  `base_rate` float NOT NULL,
  `category` varchar(50) DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `rooms`
--

INSERT INTO `rooms` (`id`, `name`, `base_rate`, `category`, `status`) VALUES
(1, 'Common Area', 35, 'solo', 'available'),
(2, 'Small Meeting Room 1', 50, 'meeting', 'available'),
(3, 'Small Meeting Room 2', 50, 'meeting', 'available'),
(4, 'Lecture Room', 150, 'lecture', 'available'),
(5, 'Conference Room', 250, 'conference', 'unavailable'),
(6, 'Comfy Room', 150, 'comfy', 'available'),
(7, 'Event Room 1', 300, 'event', 'available'),
(8, 'Event Room 2', 300, 'event', 'available'),
(37, 'Duplicate Room 322a', 50, 'standard', 'available'),
(38, 'Duplicate Room 322a', 50, 'standard', 'available'),
(39, 'Duplicate Room 78cd', 50, 'standard', 'available'),
(40, 'Duplicate Room 78cd', 50, 'standard', 'available');

-- --------------------------------------------------------

--
-- Table structure for table `solo_plans`
--

CREATE TABLE `solo_plans` (
  `id` int(11) NOT NULL,
  `customer_id` int(11) DEFAULT NULL,
  `user_id` int(11) NOT NULL,
  `approved_by_id` int(11) DEFAULT NULL,
  `plan_name` varchar(64) NOT NULL,
  `status` varchar(20) DEFAULT NULL,
  `payment_method` varchar(50) DEFAULT NULL,
  `receipt_image` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `expiry_date` datetime DEFAULT NULL,
  `is_paused` tinyint(1) DEFAULT 0,
  `paused_at` datetime DEFAULT NULL,
  `accumulated_paused_seconds` int(11) DEFAULT 0,
  `renewed_at` datetime DEFAULT NULL,
  `member_notification_seen` tinyint(1) DEFAULT 0,
  `renewal_notification_seen` tinyint(1) DEFAULT 0,
  `approved_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `solo_plans`
--

INSERT INTO `solo_plans` (`id`, `customer_id`, `user_id`, `approved_by_id`, `plan_name`, `status`, `payment_method`, `receipt_image`, `created_at`, `expiry_date`, `is_paused`, `paused_at`, `accumulated_paused_seconds`, `renewed_at`, `member_notification_seen`, `renewal_notification_seen`, `approved_at`) VALUES
(25, 103, 102, 3, 'INDIVIDUAL RATE', 'checked_out', 'GCash', 'receipt_102_1790042802.jpg', '2026-09-22 10:06:42', '2026-09-22 11:09:24', 0, NULL, 0, NULL, 1, 1, '2026-09-22 10:06:46'),
(26, 104, 102, 3, 'INDIVIDUAL RATE (4HRS)', 'checked_out', 'GCash', 'receipt_102_1790043310.jpg', '2026-09-22 10:15:10', '2026-09-22 14:15:18', 0, NULL, 0, NULL, 1, 1, '2026-09-22 10:15:14');

-- --------------------------------------------------------

--
-- Table structure for table `time_logs`
--

CREATE TABLE `time_logs` (
  `id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `plan` varchar(64) DEFAULT NULL,
  `time_in` datetime DEFAULT NULL,
  `time_out` datetime DEFAULT NULL,
  `total_time` int(11) DEFAULT NULL,
  `is_paused` tinyint(1) DEFAULT 0,
  `paused_at` datetime DEFAULT NULL,
  `accumulated_paused_seconds` int(11) DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int(11) NOT NULL,
  `customer_id` int(11) DEFAULT NULL,
  `membership_id` varchar(20) DEFAULT NULL,
  `name` varchar(64) NOT NULL,
  `email` varchar(120) NOT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL,
  `role` varchar(20) DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `expiry_date` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `failed_login_attempts` int(11) DEFAULT 0,
  `last_failed_login` datetime DEFAULT NULL,
  `locked_until` datetime DEFAULT NULL,
  `created_via_manage_staff` tinyint(1) DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `customer_id`, `membership_id`, `name`, `email`, `phone`, `password`, `role`, `is_active`, `expiry_date`, `created_at`, `failed_login_attempts`, `last_failed_login`, `locked_until`, `created_via_manage_staff`) VALUES
(3, NULL, NULL, 'wslounge', 'wslounge@lounge.com', '09171111111', 'scrypt:32768:8:1$S8oZSVmuHbX7Vyqp$95cda42d51e6f347165db2a074d4ae78d919bf709609c47438662a3eb5dc0500ad9fc4b8ae134ab044219aae006819ee22afb9af4f780d46ef2a0f47294e213a', 'admin', 1, NULL, '2026-06-07 14:52:34', 0, NULL, NULL, 0),
(102, NULL, NULL, 'lyza', 'kingrsg1999@gmail.com', '07023243673', 'scrypt:32768:8:1$r3Gjwtl1yP9JYYHH$bbcbd25876ae898265f664b4a712a8691058be8d686ad2cf071fae7ec681f20aea18aced3cd0950995a439c0b1a8fa7f11a64d51938b44dec9002ffe1ae395d5', 'member', 1, NULL, '2026-09-22 02:04:25', 0, NULL, NULL, 0);

-- --------------------------------------------------------

--
-- Table structure for table `user_activity_logs`
--

CREATE TABLE `user_activity_logs` (
  `id` int(11) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `activity_type` varchar(50) DEFAULT NULL,
  `activity_time` datetime DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `user_activity_logs`
--

INSERT INTO `user_activity_logs` (`id`, `user_id`, `activity_type`, `activity_time`, `ip_address`) VALUES
(111, 102, 'attendance|Check-In', '2026-09-22 10:07:21', '127.0.0.1'),
(112, 102, 'attendance|Paused', '2026-09-22 10:07:50', '127.0.0.1'),
(113, 102, 'attendance|Resumed', '2026-09-22 10:09:47', '127.0.0.1'),
(114, 102, 'attendance|Paused', '2026-09-22 10:12:07', '127.0.0.1'),
(115, 102, 'attendance|Resumed', '2026-09-22 10:12:13', '127.0.0.1'),
(116, 102, 'attendance|Checked-Out', '2026-09-22 10:14:25', '127.0.0.1'),
(117, 102, 'attendance|Check-In', '2026-09-22 10:15:18', '127.0.0.1'),
(118, 102, 'attendance|Checked-Out', '2026-09-22 10:15:29', '127.0.0.1');

-- --------------------------------------------------------

--
-- Table structure for table `walkin_addons`
--

CREATE TABLE `walkin_addons` (
  `id` int(11) NOT NULL,
  `walkin_reservation_id` int(11) NOT NULL,
  `addon_id` int(11) NOT NULL,
  `quantity` int(11) NOT NULL,
  `unit_price` float NOT NULL,
  `subtotal` float DEFAULT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `walkin_reservations`
--

CREATE TABLE `walkin_reservations` (
  `id` int(11) NOT NULL,
  `reservation_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `room_id` int(11) NOT NULL,
  `customer_name` varchar(64) DEFAULT NULL,
  `contact_number` varchar(20) DEFAULT NULL,
  `pax_count` int(11) DEFAULT NULL,
  `start_time` datetime NOT NULL,
  `end_time` datetime DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `total_amount` float DEFAULT NULL,
  `paid` tinyint(1) DEFAULT NULL,
  `extra_fee` float DEFAULT NULL,
  `added_by` varchar(64) DEFAULT NULL,
  `extra_notes` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `addon_name` varchar(64) DEFAULT NULL,
  `addon_quantity` int(11) DEFAULT 0,
  `addon_total` float DEFAULT 0,
  `addon_subtotal` float NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `walkin_reservations`
--

INSERT INTO `walkin_reservations` (`id`, `reservation_id`, `user_id`, `room_id`, `customer_name`, `contact_number`, `pax_count`, `start_time`, `end_time`, `status`, `total_amount`, `paid`, `extra_fee`, `added_by`, `extra_notes`, `created_at`, `addon_name`, `addon_quantity`, `addon_total`, `addon_subtotal`) VALUES
(17, 31, 3, 5, 'junard', '09742034234', 1, '2026-09-22 09:47:57', '2026-09-22 09:47:57', 'Walk-in', 250, 0, 0, 'wslounge', NULL, '2026-09-22 09:47:58', NULL, 0, 0, 0),
(18, 32, 3, 1, 'darwen', '09742034234', 1, '2026-09-22 09:58:45', '2026-09-22 10:12:34', 'Checked-Out', 10, 1, 0, 'wslounge', NULL, '2026-09-22 09:58:46', NULL, 0, 0, 0);

--
-- Indexes for dumped tables
--

--
-- Indexes for table `addons`
--
ALTER TABLE `addons`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indexes for table `attendance_logs`
--
ALTER TABLE `attendance_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `membership_id` (`membership_id`);

--
-- Indexes for table `daily_reports`
--
ALTER TABLE `daily_reports`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `report_date` (`report_date`);

--
-- Indexes for table `equipment`
--
ALTER TABLE `equipment`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `inventory`
--
ALTER TABLE `inventory`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `memberships`
--
ALTER TABLE `memberships`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `user_id` (`user_id`);

--
-- Indexes for table `payment_info`
--
ALTER TABLE `payment_info`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `method` (`method`);

--
-- Indexes for table `reservations`
--
ALTER TABLE `reservations`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `customer_id` (`customer_id`),
  ADD KEY `user_id` (`user_id`),
  ADD KEY `room_id` (`room_id`),
  ADD KEY `approved_by_id` (`approved_by_id`);

--
-- Indexes for table `reservation_addons`
--
ALTER TABLE `reservation_addons`
  ADD PRIMARY KEY (`id`),
  ADD KEY `reservation_id` (`reservation_id`),
  ADD KEY `addon_id` (`addon_id`);

--
-- Indexes for table `rooms`
--
ALTER TABLE `rooms`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `solo_plans`
--
ALTER TABLE `solo_plans`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `customer_id` (`customer_id`),
  ADD KEY `user_id` (`user_id`),
  ADD KEY `approved_by_id` (`approved_by_id`);

--
-- Indexes for table `time_logs`
--
ALTER TABLE `time_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user_id` (`user_id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `email` (`email`),
  ADD UNIQUE KEY `customer_id` (`customer_id`),
  ADD UNIQUE KEY `membership_id` (`membership_id`);

--
-- Indexes for table `user_activity_logs`
--
ALTER TABLE `user_activity_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user_id` (`user_id`);

--
-- Indexes for table `walkin_addons`
--
ALTER TABLE `walkin_addons`
  ADD PRIMARY KEY (`id`),
  ADD KEY `walkin_reservation_id` (`walkin_reservation_id`),
  ADD KEY `addon_id` (`addon_id`);

--
-- Indexes for table `walkin_reservations`
--
ALTER TABLE `walkin_reservations`
  ADD PRIMARY KEY (`id`),
  ADD KEY `reservation_id` (`reservation_id`),
  ADD KEY `user_id` (`user_id`),
  ADD KEY `room_id` (`room_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `addons`
--
ALTER TABLE `addons`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `attendance_logs`
--
ALTER TABLE `attendance_logs`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=28;

--
-- AUTO_INCREMENT for table `daily_reports`
--
ALTER TABLE `daily_reports`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `equipment`
--
ALTER TABLE `equipment`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=6;

--
-- AUTO_INCREMENT for table `inventory`
--
ALTER TABLE `inventory`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `memberships`
--
ALTER TABLE `memberships`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

--
-- AUTO_INCREMENT for table `payment_info`
--
ALTER TABLE `payment_info`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT for table `reservations`
--
ALTER TABLE `reservations`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=35;

--
-- AUTO_INCREMENT for table `reservation_addons`
--
ALTER TABLE `reservation_addons`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `rooms`
--
ALTER TABLE `rooms`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=41;

--
-- AUTO_INCREMENT for table `solo_plans`
--
ALTER TABLE `solo_plans`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=27;

--
-- AUTO_INCREMENT for table `time_logs`
--
ALTER TABLE `time_logs`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=103;

--
-- AUTO_INCREMENT for table `user_activity_logs`
--
ALTER TABLE `user_activity_logs`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=119;

--
-- AUTO_INCREMENT for table `walkin_addons`
--
ALTER TABLE `walkin_addons`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `walkin_reservations`
--
ALTER TABLE `walkin_reservations`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=19;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `attendance_logs`
--
ALTER TABLE `attendance_logs`
  ADD CONSTRAINT `attendance_logs_ibfk_1` FOREIGN KEY (`membership_id`) REFERENCES `memberships` (`id`);

--
-- Constraints for table `memberships`
--
ALTER TABLE `memberships`
  ADD CONSTRAINT `memberships_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `reservations`
--
ALTER TABLE `reservations`
  ADD CONSTRAINT `reservations_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `reservations_ibfk_2` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`),
  ADD CONSTRAINT `reservations_ibfk_3` FOREIGN KEY (`approved_by_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `reservation_addons`
--
ALTER TABLE `reservation_addons`
  ADD CONSTRAINT `reservation_addons_ibfk_1` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `reservation_addons_ibfk_2` FOREIGN KEY (`addon_id`) REFERENCES `addons` (`id`);

--
-- Constraints for table `solo_plans`
--
ALTER TABLE `solo_plans`
  ADD CONSTRAINT `solo_plans_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `solo_plans_ibfk_2` FOREIGN KEY (`approved_by_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `time_logs`
--
ALTER TABLE `time_logs`
  ADD CONSTRAINT `time_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `user_activity_logs`
--
ALTER TABLE `user_activity_logs`
  ADD CONSTRAINT `user_activity_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `walkin_addons`
--
ALTER TABLE `walkin_addons`
  ADD CONSTRAINT `walkin_addons_ibfk_1` FOREIGN KEY (`walkin_reservation_id`) REFERENCES `walkin_reservations` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `walkin_addons_ibfk_2` FOREIGN KEY (`addon_id`) REFERENCES `addons` (`id`);

--
-- Constraints for table `walkin_reservations`
--
ALTER TABLE `walkin_reservations`
  ADD CONSTRAINT `walkin_reservations_ibfk_1` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `walkin_reservations_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `walkin_reservations_ibfk_3` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
