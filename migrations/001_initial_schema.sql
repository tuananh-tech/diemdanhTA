-- HỆ THỐNG ĐIỂM DANH TNTT – lược đồ PostgreSQL / Supabase
-- Phiên bản lược đồ: 1. File được sinh tự động từ tntt/models.py – KHÔNG sửa tay.
-- Ứng dụng tự tạo bảng khi khởi động; chỉ chạy file này nếu muốn khởi tạo thủ công.
BEGIN;

CREATE TABLE app_settings (
	key VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE branches (
	id SERIAL NOT NULL, 
	name VARCHAR(60) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	color VARCHAR(9) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE schema_meta (
	id SERIAL NOT NULL, 
	version INTEGER NOT NULL, 
	applied_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE school_years (
	id SERIAL NOT NULL, 
	name VARCHAR(20) NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	semester2_start DATE, 
	is_current BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE students (
	id SERIAL NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	saint_name VARCHAR(60), 
	full_name VARCHAR(120) NOT NULL, 
	search_text VARCHAR(255) NOT NULL, 
	birth_date DATE, 
	gender VARCHAR(1), 
	parent_name VARCHAR(120), 
	parent_phone VARCHAR(30), 
	note VARCHAR(255), 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_students_status CHECK (status IN ('active', 'inactive', 'moved', 'graduated')), 
	UNIQUE (code)
);
CREATE INDEX ix_students_search_text ON students (search_text);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	must_change_password BOOLEAN NOT NULL, 
	failed_attempts INTEGER NOT NULL, 
	locked_until TIMESTAMP WITHOUT TIME ZONE, 
	last_login_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_role CHECK (role IN ('admin', 'coordinator', 'leader', 'viewer')), 
	UNIQUE (username)
);

CREATE TABLE assets (
	key VARCHAR(64) NOT NULL, 
	data BYTEA NOT NULL, 
	mime VARCHAR(40) NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_by INTEGER, 
	PRIMARY KEY (key), 
	FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE attendance_sessions (
	id SERIAL NOT NULL, 
	uid VARCHAR(32) NOT NULL, 
	school_year_id INTEGER NOT NULL, 
	title VARCHAR(150) NOT NULL, 
	activity_type VARCHAR(60) NOT NULL, 
	session_date DATE NOT NULL, 
	start_time TIME WITHOUT TIME ZONE, 
	late_after TIME WITHOUT TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	scope_all BOOLEAN NOT NULL, 
	owner_id INTEGER, 
	note VARCHAR(255), 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	opened_at TIMESTAMP WITHOUT TIME ZONE, 
	closed_at TIMESTAMP WITHOUT TIME ZONE, 
	closed_by INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_sessions_status CHECK (status IN ('scheduled', 'open', 'closed')), 
	UNIQUE (uid), 
	FOREIGN KEY(school_year_id) REFERENCES school_years (id) ON DELETE RESTRICT, 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(closed_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_sessions_year_date ON attendance_sessions (school_year_id, session_date);

CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	user_id INTEGER, 
	username VARCHAR(64), 
	action VARCHAR(60) NOT NULL, 
	entity VARCHAR(40), 
	entity_id VARCHAR(64), 
	details TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_audit_at ON audit_logs (at);

CREATE TABLE classes (
	id SERIAL NOT NULL, 
	school_year_id INTEGER NOT NULL, 
	branch_id INTEGER, 
	name VARCHAR(60) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	note VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_class_year_name UNIQUE (school_year_id, name), 
	FOREIGN KEY(school_year_id) REFERENCES school_years (id) ON DELETE RESTRICT, 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE SET NULL
);
CREATE INDEX ix_classes_school_year_id ON classes (school_year_id);

CREATE TABLE face_consents (
	id SERIAL NOT NULL, 
	student_id INTEGER NOT NULL, 
	guardian_name VARCHAR(120) NOT NULL, 
	relation VARCHAR(40) NOT NULL, 
	consent_date DATE NOT NULL, 
	expires_at DATE NOT NULL, 
	document_ref VARCHAR(120) NOT NULL, 
	recorded_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	withdrawn_at TIMESTAMP WITHOUT TIME ZONE, 
	withdrawn_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(recorded_by) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(withdrawn_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_face_consents_student_id ON face_consents (student_id);

CREATE TABLE login_sessions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	user_agent VARCHAR(255), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	UNIQUE (token_hash)
);
CREATE INDEX ix_login_sessions_user_id ON login_sessions (user_id);

CREATE TABLE qr_credentials (
	id SERIAL NOT NULL, 
	student_id INTEGER NOT NULL, 
	token VARCHAR(40) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	issued_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	issued_by INTEGER, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	revoked_by INTEGER, 
	revoke_reason VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_qr_status CHECK (status IN ('active', 'revoked')), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	UNIQUE (token), 
	FOREIGN KEY(issued_by) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(revoked_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX uq_qr_one_active_per_student ON qr_credentials (student_id) WHERE status = 'active';

CREATE TABLE attendance_records (
	id SERIAL NOT NULL, 
	session_id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	class_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	method VARCHAR(20), 
	note VARCHAR(255), 
	marked_by INTEGER, 
	marked_at TIMESTAMP WITHOUT TIME ZONE, 
	version INTEGER DEFAULT 1 NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_record_session_student UNIQUE (session_id, student_id), 
	CONSTRAINT ck_records_status CHECK (status IN ('unmarked', 'present', 'late', 'excused', 'absent')), 
	FOREIGN KEY(session_id) REFERENCES attendance_sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(class_id) REFERENCES classes (id) ON DELETE SET NULL, 
	FOREIGN KEY(marked_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_records_student ON attendance_records (student_id);

CREATE TABLE enrollments (
	id SERIAL NOT NULL, 
	student_id INTEGER NOT NULL, 
	school_year_id INTEGER NOT NULL, 
	class_id INTEGER, 
	team VARCHAR(60), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_enrollment_student_year UNIQUE (student_id, school_year_id), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(school_year_id) REFERENCES school_years (id) ON DELETE RESTRICT, 
	FOREIGN KEY(class_id) REFERENCES classes (id) ON DELETE SET NULL
);
CREATE INDEX ix_enrollments_class_id ON enrollments (class_id);
CREATE INDEX ix_enrollments_school_year_id ON enrollments (school_year_id);

CREATE TABLE face_templates (
	id SERIAL NOT NULL, 
	student_id INTEGER NOT NULL, 
	consent_id INTEGER NOT NULL, 
	model VARCHAR(40) NOT NULL, 
	vector BYTEA NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(consent_id) REFERENCES face_consents (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_face_templates_student_id ON face_templates (student_id);

CREATE TABLE session_classes (
	session_id INTEGER NOT NULL, 
	class_id INTEGER NOT NULL, 
	PRIMARY KEY (session_id, class_id), 
	FOREIGN KEY(session_id) REFERENCES attendance_sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(class_id) REFERENCES classes (id) ON DELETE CASCADE
);

CREATE TABLE user_scopes (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	branch_id INTEGER, 
	class_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_scope_target CHECK (branch_id IS NOT NULL OR class_id IS NOT NULL), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE CASCADE, 
	FOREIGN KEY(class_id) REFERENCES classes (id) ON DELETE CASCADE
);
CREATE INDEX ix_user_scopes_user_id ON user_scopes (user_id);

CREATE TABLE attendance_logs (
	id SERIAL NOT NULL, 
	record_id INTEGER, 
	session_id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	old_status VARCHAR(20), 
	new_status VARCHAR(20) NOT NULL, 
	method VARCHAR(20), 
	note VARCHAR(255), 
	user_id INTEGER, 
	at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(record_id) REFERENCES attendance_records (id) ON DELETE SET NULL, 
	FOREIGN KEY(session_id) REFERENCES attendance_sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_attlog_session ON attendance_logs (session_id);

-- Supabase mở REST API công khai cho schema public: bật RLS (không policy) để khóa truy cập
-- bằng anon/authenticated key. Ứng dụng kết nối bằng vai trò chủ sở hữu bảng nên không bị ảnh hưởng.
ALTER TABLE "app_settings" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "branches" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "schema_meta" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "school_years" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "students" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "users" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "assets" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "attendance_sessions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "audit_logs" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "classes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "face_consents" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "login_sessions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "qr_credentials" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "attendance_records" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "enrollments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "face_templates" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "session_classes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user_scopes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "attendance_logs" ENABLE ROW LEVEL SECURITY;

INSERT INTO schema_meta (version, applied_at) VALUES (1, now());
COMMIT;
