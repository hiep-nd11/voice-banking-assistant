-- =====================================================================
-- Voice Banking Assistant (Smart Banking 2026 AI Hackathon)
-- Schema PostgreSQL >= 14, tên schema: vb
-- Toàn bộ dữ liệu là MOCK / tổng hợp (synthetic), không có dữ liệu khách hàng thật.
--
-- Nguyên tắc:
--  * Mọi con số đọc cho khách hàng đều do SQL/tool tính, LLM chỉ diễn giải.
--  * Agent KHÔNG thực hiện giao dịch. Nó chỉ tạo "pending_actions" (bản nháp mở màn hình +
--    điền sẵn), khách hàng tự nhập phần còn lại và tự xác nhận trên app.
--  * Mọi lần gọi tool đều ghi tool_audit_log.
-- =====================================================================

DROP SCHEMA IF EXISTS vb CASCADE;
CREATE SCHEMA vb;
SET search_path TO vb;

-- ---------- 1. Khách hàng ----------
CREATE TABLE customers (
    customer_id      VARCHAR(20) PRIMARY KEY,               -- KH0001
    full_name        VARCHAR(100) NOT NULL,
    salutation       VARCHAR(30)  NOT NULL,                  -- cách agent xưng hô: "anh Hưng", "bác Bảy"
    date_of_birth    DATE,
    gender           VARCHAR(10),                            -- nam / nu
    occupation       VARCHAR(100),
    city             VARCHAR(50),
    segment          VARCHAR(20)  NOT NULL DEFAULT 'mass',   -- mass / affluent / priority
    accessibility_needs VARCHAR(100),                        -- vd: "lão thị, khó đọc chữ nhỏ"
    persona_note     TEXT,                                   -- mô tả persona dùng khi demo
    created_at       TIMESTAMP NOT NULL DEFAULT now()
);

-- ---------- 1b. Sản phẩm (MOCK, không phải biểu lãi suất thật) ----------
CREATE TABLE products (
    product_code     VARCHAR(30) PRIMARY KEY,
    name_vi          VARCHAR(150) NOT NULL,
    product_type     VARCHAR(20) NOT NULL CHECK (product_type IN ('savings','loan')),
    short_desc       TEXT NOT NULL,
    interest_rate    NUMERIC(5,2),                           -- %/năm, MOCK
    term_months      SMALLINT,
    min_amount       NUMERIC(15,0),
    max_amount       NUMERIC(15,0),
    max_term_months  SMALLINT,
    channel          VARCHAR(20) NOT NULL DEFAULT 'app',     -- app / branch
    is_mock          BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------- 2. Tài khoản ----------
-- Mỗi khách có đúng 1 tài khoản thanh toán (payment). Mọi giao dịch nằm trên tài khoản này.
-- Sổ tiết kiệm (savings) và khoản vay (loan) nằm "trong" tài khoản thanh toán: parent_account_id trỏ về
-- tài khoản thanh toán; gửi/tất toán sổ, nhận lãi, trích nợ trả góp đều hiện là giao dịch trên tài khoản cha.
CREATE TABLE accounts (
    account_id       VARCHAR(20) PRIMARY KEY,                -- TK000101
    customer_id      VARCHAR(20) NOT NULL REFERENCES customers(customer_id),
    parent_account_id VARCHAR(20) REFERENCES accounts(account_id),
    account_number   VARCHAR(20) NOT NULL UNIQUE,            -- savings: số sổ, loan: số hợp đồng vay
    account_type     VARCHAR(20) NOT NULL
                     CHECK (account_type IN ('payment','savings','loan')),
    nickname         VARCHAR(60),                            -- "Tài khoản thanh toán", "Sổ tiết kiệm 12 tháng"
    product_code     VARCHAR(30) REFERENCES products(product_code),
    balance          NUMERIC(15,0) NOT NULL DEFAULT 0,       -- payment: số dư lúc sinh dữ liệu (tool tính số dư
                                                             --   "tính đến hôm nay" từ balance_after)
                                                             -- savings: tiền gốc; loan: dư nợ gốc (số dương)
    interest_rate    NUMERIC(5,2),                           -- %/năm, MOCK
    term_months      SMALLINT,
    opened_at        DATE NOT NULL,
    maturity_date    DATE,                                   -- savings / loan
    monthly_payment  NUMERIC(15,0),                          -- loan: số tiền trả góp mỗi tháng
    status           VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed')),
    currency         CHAR(3) NOT NULL DEFAULT 'VND',
    CHECK ((account_type = 'payment') = (parent_account_id IS NULL))
);
CREATE INDEX idx_accounts_customer ON accounts(customer_id);
CREATE UNIQUE INDEX uq_one_payment_account ON accounts(customer_id) WHERE account_type = 'payment';

-- ---------- 3. Danh mục ----------
CREATE TABLE categories (
    category_code    VARCHAR(30) PRIMARY KEY,
    name_vi          VARCHAR(60) NOT NULL,
    group_code       VARCHAR(20) NOT NULL
                     CHECK (group_code IN ('income','needs','wants','savings','internal')),
    direction        VARCHAR(3)  NOT NULL CHECK (direction IN ('in','out')),
    is_spending      BOOLEAN NOT NULL DEFAULT FALSE,         -- tính vào "chi tiêu"
    is_income        BOOLEAN NOT NULL DEFAULT FALSE,         -- tính vào "thu nhập"
    keywords         TEXT                                    -- từ khóa tiếng Việt để tool map câu hỏi -> danh mục
);

-- ---------- 4. Giao dịch ----------
CREATE TABLE transactions (
    txn_id           BIGSERIAL PRIMARY KEY,
    account_id       VARCHAR(20) NOT NULL REFERENCES accounts(account_id),
    txn_time         TIMESTAMP NOT NULL,                     -- giờ Việt Nam
    amount           NUMERIC(15,0) NOT NULL CHECK (amount > 0),
    direction        VARCHAR(3) NOT NULL CHECK (direction IN ('in','out')),
    channel          VARCHAR(20) NOT NULL,                   -- transfer / qr / card (thẻ ghi nợ) / bill / atm / salary / auto_debit / internal / interest
    description      TEXT NOT NULL,                          -- nội dung thô như sao kê (không dấu)
    counterparty_name    VARCHAR(100),
    counterparty_account VARCHAR(30),
    counterparty_bank    VARCHAR(30),
    merchant         VARCHAR(100),
    category_code    VARCHAR(30) REFERENCES categories(category_code),
    balance_after    NUMERIC(15,0),
    is_anomaly_seed  BOOLEAN NOT NULL DEFAULT FALSE,         -- nhãn để CHẤM EVAL. Tool/agent KHÔNG được đọc cột này.
    anomaly_note     TEXT                                    -- mô tả ca bất thường cài sẵn (chỉ cho eval)
);
CREATE INDEX idx_txn_account_time ON transactions(account_id, txn_time);
CREATE INDEX idx_txn_category     ON transactions(category_code);
CREATE INDEX idx_txn_cp_account   ON transactions(counterparty_account);

-- Giao dịch chỉ được ghi trên tài khoản thanh toán (sổ tiết kiệm / khoản vay không có giao dịch riêng).
CREATE FUNCTION txn_payment_account_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT account_type FROM vb.accounts WHERE account_id = NEW.account_id) <> 'payment' THEN
        RAISE EXCEPTION 'Giao dịch % phải thuộc tài khoản thanh toán', NEW.account_id;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_txn_payment_account_only BEFORE INSERT OR UPDATE OF account_id ON transactions
    FOR EACH ROW EXECUTE FUNCTION txn_payment_account_only();

-- ---------- 5. Danh bạ người nhận đã lưu ----------
CREATE TABLE beneficiaries (
    beneficiary_id   BIGSERIAL PRIMARY KEY,
    customer_id      VARCHAR(20) NOT NULL REFERENCES customers(customer_id),
    display_name     VARCHAR(100) NOT NULL,                  -- "Lê Thị Mai"
    relationship     VARCHAR(30),                            -- vợ / con trai / mẹ / ...
    aliases          TEXT[] NOT NULL DEFAULT '{}',           -- cách khách hay gọi: {"vợ","bà xã","mai"}
    account_number   VARCHAR(30) NOT NULL,
    bank_name        VARCHAR(50) NOT NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (customer_id, account_number)
);

-- ---------- 7. Thao tác agent đã chuẩn bị (KHÔNG phải giao dịch) ----------
-- Agent chỉ được tạo bản ghi ở đây. Màn hình app đọc prefill, khách tự nhập phần còn lại,
-- tự xác nhận (OTP/sinh trắc học) - phần thực hiện giao dịch nằm ngoài agent.
CREATE TABLE pending_actions (
    action_id        VARCHAR(40) PRIMARY KEY,                -- act_xxx
    customer_id      VARCHAR(20) NOT NULL REFERENCES customers(customer_id),
    action_type      VARCHAR(20) NOT NULL CHECK (action_type IN ('transfer','savings','loan')),
    screen           VARCHAR(40) NOT NULL,                   -- route của app: transfer / savings_open / loan_apply
    prefill          JSONB NOT NULL,                         -- {amount, beneficiary?, term_months?, ...}
    required_user_inputs TEXT[] NOT NULL,                    -- những gì khách phải tự nhập/xác nhận
    risk             JSONB,                                  -- kết quả check_transfer_risk lúc tạo
    status           VARCHAR(15) NOT NULL DEFAULT 'created'
                     CHECK (status IN ('created','opened','submitted','cancelled','expired')),
    session_id       VARCHAR(64),
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    updated_at       TIMESTAMP NOT NULL DEFAULT now(),
    expires_at       TIMESTAMP NOT NULL
);
CREATE INDEX idx_actions_customer ON pending_actions(customer_id, created_at DESC);

-- ---------- 8. Nhật ký gọi tool (audit) ----------
CREATE TABLE tool_audit_log (
    log_id           BIGSERIAL PRIMARY KEY,
    customer_id      VARCHAR(20),
    session_id       VARCHAR(64),
    tool_name        VARCHAR(50) NOT NULL,
    arguments        JSONB,
    result_summary   TEXT,
    is_error         BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms       INTEGER,
    model_name       VARCHAR(60),
    created_at       TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_customer ON tool_audit_log(customer_id, created_at DESC);

-- ---------- View: giao dịch kèm khách hàng + danh mục ----------
-- Không đưa is_anomaly_seed / anomaly_note vào view -> tool chỉ đọc view này.
CREATE VIEW v_txn AS
SELECT t.txn_id, a.customer_id, t.account_id, a.account_type, a.nickname AS account_nickname,
       t.txn_time, t.amount, t.direction, t.channel, t.description,
       t.counterparty_name, t.counterparty_account, t.counterparty_bank, t.merchant,
       t.category_code, c.name_vi AS category_name, c.group_code, c.is_spending, c.is_income,
       t.balance_after
FROM transactions t
JOIN accounts a        ON a.account_id = t.account_id
LEFT JOIN categories c ON c.category_code = t.category_code;
