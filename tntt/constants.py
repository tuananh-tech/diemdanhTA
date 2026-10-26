"""Hằng số nghiệp vụ dùng chung."""
from __future__ import annotations

# ---- Trạng thái điểm danh -------------------------------------------------
UNMARKED = "unmarked"
PRESENT = "present"
LATE = "late"
EXCUSED = "excused"
ABSENT = "absent"

STATUSES = [UNMARKED, PRESENT, LATE, EXCUSED, ABSENT]
MARKED_STATUSES = [PRESENT, LATE, EXCUSED, ABSENT]
ATTENDED_STATUSES = [PRESENT, LATE]

STATUS_LABELS = {
    UNMARKED: "Chưa điểm danh",
    PRESENT: "Có mặt",
    LATE: "Đi trễ",
    EXCUSED: "Vắng có phép",
    ABSENT: "Vắng không phép",
}
STATUS_SHORT = {
    PRESENT: "Có mặt",
    LATE: "Trễ",
    EXCUSED: "Phép",
    ABSENT: "Vắng",
}
STATUS_COLORS = {
    UNMARKED: "#9AA3B2",
    PRESENT: "#2E8B57",
    LATE: "#D4A017",
    EXCUSED: "#3B6FB6",
    ABSENT: "#C0392B",
}

# ---- Phương thức ghi nhận --------------------------------------------------
METHOD_MANUAL = "manual"
METHOD_QR = "qr"
METHOD_CODE = "code"  # nhập mã thủ công tại trang quét
METHOD_BULK = "bulk"
METHOD_FACE = "face"
METHOD_SYSTEM = "system"
METHOD_LABELS = {
    METHOD_MANUAL: "Thủ công",
    METHOD_QR: "Quét QR",
    METHOD_CODE: "Nhập mã",
    METHOD_BULK: "Hàng loạt",
    METHOD_FACE: "Khuôn mặt (đã xác nhận)",
    METHOD_SYSTEM: "Hệ thống",
}

# ---- Phiên điểm danh -------------------------------------------------------
SESSION_SCHEDULED = "scheduled"
SESSION_OPEN = "open"
SESSION_CLOSED = "closed"
SESSION_STATUS_LABELS = {
    SESSION_SCHEDULED: "Đã lên lịch",
    SESSION_OPEN: "Đang mở",
    SESSION_CLOSED: "Đã đóng",
}
ACTIVITY_TYPES = ["Thánh lễ", "Giáo lý", "Sinh hoạt TNTT", "Chầu Thánh Thể", "Sinh hoạt ngoại khóa", "Khác"]

# ---- Thiếu nhi -------------------------------------------------------------
STUDENT_STATUS_LABELS = {
    "active": "Đang sinh hoạt",
    "inactive": "Tạm nghỉ",
    "moved": "Chuyển xứ",
    "graduated": "Đã trưởng thành",
}
GENDER_LABELS = {"": "—", "M": "Nam", "F": "Nữ"}

DEFAULT_BRANCHES = [
    ("Chiên Con", "#F2C94C"),
    ("Ấu Nhi", "#27AE60"),
    ("Thiếu Nhi", "#2F80ED"),
    ("Nghĩa Sĩ", "#EB5757"),
    ("Hiệp Sĩ", "#8B5E3C"),
]

# ---- Vai trò ---------------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_COORDINATOR = "coordinator"
ROLE_LEADER = "leader"
ROLE_VIEWER = "viewer"
ROLE_LABELS = {
    ROLE_ADMIN: "Quản trị hệ thống",
    ROLE_COORDINATOR: "Ban Điều hành Xứ đoàn",
    ROLE_LEADER: "Huynh trưởng / Dự trưởng",
    ROLE_VIEWER: "Chỉ xem",
}
