"""
SQL Practice Lab — app.py
Single-file Streamlit application for practicing MySQL and SQL Server queries
using an in-memory SQLite engine with automatic dialect translation via sqlglot.
No external database required. No credentials. No file I/O.
"""

import sqlite3
import time
import re
import datetime
import pandas as pd

import streamlit as st
import sqlglot
import sqlglot.errors as sqlglot_errors

try:
    from streamlit_ace import st_ace
    ACE_AVAILABLE = True
except ImportError:
    ACE_AVAILABLE = False

# ═══════════════════════════════════════════════════════════
# CONSTANTS — st.session_state keys (all keys documented here)
# ═══════════════════════════════════════════════════════════
SK_CONN        = "db_conn"         # sqlite3.Connection (in-memory, per session)
SK_DIALECT     = "dialect"         # str: "mysql" | "sqlserver"
SK_DATASET     = "dataset"         # str: "employees" | "orders" | "library" | "hospital"
SK_EDITOR_SQL  = "editor_sql"      # str: current SQL text shown in editor
SK_EDITOR_KEY  = "editor_key"      # int: increment to force ACE editor re-render
SK_HISTORY     = "query_history"   # list[dict]: {timestamp, sql, rows}
SK_LAST_RESULT = "last_result"     # dict: last run_query() return value
SK_ACTIVE_Q    = "active_question" # int|None: currently selected question id

DATASETS = ["employees", "orders", "library", "hospital"]
DIALECTS = {"MySQL": "mysql", "SQL Server": "sqlserver"}
MAX_HISTORY = 10

ALL_TABLES = {
    "employees": ["departments", "employees", "salaries"],
    "orders":    ["customers", "products", "orders", "order_items"],
    "library":   ["members", "books", "loans"],
    "hospital":  ["doctors", "patients", "appointments", "prescriptions"],
}

# ═══════════════════════════════════════════════════════════
# SEED DATA — schema DDL + INSERT statements per dataset
# ═══════════════════════════════════════════════════════════

SCHEMA_SQL: dict[str, str] = {

# ── employees ──────────────────────────────────────────────
"employees": """
CREATE TABLE departments (
    dept_id   INTEGER PRIMARY KEY,
    dept_name TEXT NOT NULL,
    location  TEXT
);
CREATE TABLE employees (
    emp_id     INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    email      TEXT UNIQUE,
    hire_date  TEXT,
    job_title  TEXT,
    dept_id    INTEGER REFERENCES departments(dept_id),
    manager_id INTEGER REFERENCES employees(emp_id)
);
CREATE TABLE salaries (
    salary_id  INTEGER PRIMARY KEY,
    emp_id     INTEGER REFERENCES employees(emp_id),
    amount     REAL NOT NULL,
    from_date  TEXT,
    to_date    TEXT
);

INSERT INTO departments VALUES
(1,'Engineering','San Francisco'),
(2,'Marketing','New York'),
(3,'Sales','Chicago'),
(4,'HR','Austin'),
(5,'Finance','Boston');

INSERT INTO employees VALUES
(1,'Alice','Johnson','alice@corp.com','2018-03-12','Software Engineer',1,NULL),
(2,'Bob','Smith','bob@corp.com','2017-06-01','Senior Engineer',1,1),
(3,'Carol','White','carol@corp.com','2019-11-20','Marketing Manager',2,NULL),
(4,'David','Brown','david@corp.com','2020-01-15','Sales Rep',3,NULL),
(5,'Eve','Davis','eve@corp.com','2016-08-30','HR Director',4,NULL),
(6,'Frank','Miller','frank@corp.com','2021-04-10','Junior Engineer',1,2),
(7,'Grace','Wilson','grace@corp.com','2022-07-01','Data Analyst',1,2),
(8,'Hank','Moore','hank@corp.com','2015-02-28','Finance Director',5,NULL),
(9,'Iris','Taylor','iris@corp.com','2023-01-09','Sales Rep',3,4),
(10,'Jack','Anderson','jack@corp.com','2019-09-17','Marketing Analyst',2,3),
(11,'Kate','Thomas','kate@corp.com','2020-05-22','Software Engineer',1,1),
(12,'Leo','Jackson','leo@corp.com','2021-12-01','HR Specialist',4,5),
(13,'Mia','Harris','mia@corp.com','2018-07-14','Senior Engineer',1,1),
(14,'Ned','Martin','ned@corp.com','2022-03-28','Sales Manager',3,NULL),
(15,'Olivia','Lee','olivia@corp.com','2017-10-05','Finance Analyst',5,8),
(16,'Paul','Garcia','paul@corp.com','2023-06-19','Junior Engineer',1,2),
(17,'Quinn','Martinez','quinn@corp.com','2019-04-03','Data Scientist',1,2),
(18,'Rachel','Robinson','rachel@corp.com','2016-11-11','Marketing Manager',2,NULL),
(19,'Sam','Clark','sam@corp.com','2020-08-25','Sales Rep',3,14),
(20,'Tina','Rodriguez','tina@corp.com','2021-02-14','Accountant',5,8);

INSERT INTO salaries VALUES
(1,1,95000,'2018-03-12','2020-03-12'),
(2,1,105000,'2020-03-12','9999-01-01'),
(3,2,130000,'2017-06-01','2021-06-01'),
(4,2,145000,'2021-06-01','9999-01-01'),
(5,3,90000,'2019-11-20','9999-01-01'),
(6,4,65000,'2020-01-15','9999-01-01'),
(7,5,110000,'2016-08-30','9999-01-01'),
(8,6,72000,'2021-04-10','9999-01-01'),
(9,7,85000,'2022-07-01','9999-01-01'),
(10,8,140000,'2015-02-28','9999-01-01'),
(11,9,62000,'2023-01-09','9999-01-01'),
(12,10,78000,'2019-09-17','9999-01-01'),
(13,11,98000,'2020-05-22','9999-01-01'),
(14,12,68000,'2021-12-01','9999-01-01'),
(15,13,135000,'2018-07-14','9999-01-01'),
(16,14,95000,'2022-03-28','9999-01-01'),
(17,15,82000,'2017-10-05','9999-01-01'),
(18,16,70000,'2023-06-19','9999-01-01'),
(19,17,115000,'2019-04-03','9999-01-01'),
(20,18,92000,'2016-11-11','9999-01-01'),
(21,19,64000,'2020-08-25','9999-01-01'),
(22,20,76000,'2021-02-14','9999-01-01');
""",

# ── orders ─────────────────────────────────────────────────
"orders": """
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    email         TEXT UNIQUE,
    city          TEXT,
    country       TEXT,
    created_at    TEXT
);
CREATE TABLE products (
    product_id    INTEGER PRIMARY KEY,
    product_name  TEXT NOT NULL,
    category      TEXT,
    unit_price    REAL NOT NULL,
    stock_qty     INTEGER DEFAULT 0
);
CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER REFERENCES customers(customer_id),
    order_date    TEXT,
    status        TEXT DEFAULT 'pending',
    total_amount  REAL
);
CREATE TABLE order_items (
    item_id       INTEGER PRIMARY KEY,
    order_id      INTEGER REFERENCES orders(order_id),
    product_id    INTEGER REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    REAL NOT NULL
);

INSERT INTO customers VALUES
(1,'James','Walker','james.w@email.com','New York','USA','2022-01-10'),
(2,'Sophia','Brown','sophia.b@email.com','London','UK','2022-02-15'),
(3,'Liam','Jones','liam.j@email.com','Toronto','Canada','2022-03-01'),
(4,'Emma','Davis','emma.d@email.com','Sydney','Australia','2022-03-20'),
(5,'Noah','Miller','noah.m@email.com','Berlin','Germany','2022-04-05'),
(6,'Ava','Wilson','ava.w@email.com','Paris','France','2022-05-12'),
(7,'Oliver','Moore','oliver.m@email.com','New York','USA','2022-06-18'),
(8,'Isabella','Taylor','isabella.t@email.com','Chicago','USA','2022-07-22'),
(9,'Elijah','Anderson','elijah.a@email.com','Los Angeles','USA','2022-08-30'),
(10,'Mia','Thomas','mia.t@email.com','Houston','USA','2022-09-14'),
(11,'Lucas','Jackson','lucas.j@email.com','Toronto','Canada','2022-10-01'),
(12,'Amelia','White','amelia.w@email.com','Melbourne','Australia','2022-10-25'),
(13,'Mason','Harris','mason.h@email.com','London','UK','2022-11-08'),
(14,'Harper','Martin','harper.m@email.com','Dublin','Ireland','2022-12-03'),
(15,'Ethan','Garcia','ethan.g@email.com','Madrid','Spain','2023-01-19'),
(16,'Charlotte','Lee','charlotte.l@email.com','Seoul','South Korea','2023-02-14'),
(17,'Benjamin','Robinson','ben.r@email.com','Tokyo','Japan','2023-03-07'),
(18,'Aria','Clark','aria.c@email.com','Singapore','Singapore','2023-04-21');

INSERT INTO products VALUES
(1,'Laptop Pro 15','Electronics',1299.99,45),
(2,'Wireless Mouse','Electronics',29.99,200),
(3,'USB-C Hub','Electronics',49.99,150),
(4,'Mechanical Keyboard','Electronics',119.99,80),
(5,'Monitor 27"','Electronics',399.99,30),
(6,'Office Chair','Furniture',249.99,20),
(7,'Standing Desk','Furniture',599.99,15),
(8,'Notebook Pack','Stationery',12.99,500),
(9,'Ballpoint Pens (12pk)','Stationery',6.99,800),
(10,'Webcam HD','Electronics',89.99,60),
(11,'Headphones Pro','Electronics',199.99,75),
(12,'Desk Lamp','Furniture',44.99,100),
(13,'Cable Organizer','Accessories',19.99,300),
(14,'Phone Stand','Accessories',15.99,250),
(15,'Whiteboard A3','Stationery',34.99,120),
(16,'Ergonomic Mouse Pad','Accessories',24.99,180),
(17,'Portable SSD 1TB','Electronics',109.99,55),
(18,'Tablet Stand','Accessories',22.99,140),
(19,'Smart Speaker','Electronics',79.99,65),
(20,'Power Strip 6-outlet','Accessories',32.99,90);

INSERT INTO orders VALUES
(1,1,'2023-01-05','completed',1459.97),
(2,2,'2023-01-12','completed',279.98),
(3,3,'2023-02-03','completed',49.99),
(4,4,'2023-02-18','shipped',649.98),
(5,5,'2023-03-07','completed',119.99),
(6,6,'2023-03-22','completed',2099.97),
(7,7,'2023-04-10','pending',89.99),
(8,8,'2023-04-25','completed',399.99),
(9,9,'2023-05-14','shipped',329.98),
(10,10,'2023-05-30','completed',1299.99),
(11,1,'2023-06-08','completed',199.99),
(12,11,'2023-06-20','completed',739.97),
(13,12,'2023-07-04','pending',44.99),
(14,13,'2023-07-19','completed',159.98),
(15,14,'2023-08-02','shipped',249.99),
(16,15,'2023-08-17','completed',79.99),
(17,3,'2023-09-01','completed',469.97),
(18,16,'2023-09-15','completed',109.99),
(19,17,'2023-10-02','completed',32.99),
(20,2,'2023-10-18','shipped',599.99),
(21,18,'2023-11-05','completed',224.98),
(22,7,'2023-11-20','completed',364.97),
(23,9,'2023-12-08','completed',149.98),
(24,5,'2023-12-22','pending',89.99);

INSERT INTO order_items VALUES
(1,1,1,1,1299.99),(2,1,2,1,29.99),(3,1,3,1,49.99),(4,1,9,2,6.99),
(5,2,6,1,249.99),(6,2,12,1,44.99),
(7,3,3,1,49.99),
(8,4,7,1,599.99),(9,4,13,1,19.99),(10,4,14,2,15.99),
(11,5,4,1,119.99),
(12,6,1,1,1299.99),(13,6,5,1,399.99),(14,6,11,2,199.99),
(15,7,10,1,89.99),
(16,8,5,1,399.99),
(17,9,11,1,199.99),(18,9,16,2,24.99),(19,9,13,4,19.99),
(20,10,1,1,1299.99),
(21,11,11,1,199.99),
(22,12,5,1,399.99),(23,12,17,1,109.99),(24,12,19,1,79.99),(25,12,2,5,29.99),
(26,13,12,1,44.99),
(27,14,8,3,12.99),(28,14,15,1,34.99),(29,14,9,5,6.99),
(30,15,6,1,249.99),
(31,16,19,1,79.99),
(32,17,1,1,1299.99),(33,17,3,1,49.99),(34,17,13,6,19.99),
(35,18,17,1,109.99),
(36,19,20,1,32.99),
(37,20,7,1,599.99),
(38,21,4,1,119.99),(39,21,16,1,24.99),(40,21,9,10,6.99),
(41,22,5,1,399.99),(42,22,2,3,29.99),(43,22,18,2,22.99),
(44,23,11,1,199.99),(45,23,13,3,19.99),
(46,24,10,1,89.99);
""",

# ── library ────────────────────────────────────────────────
"library": """
CREATE TABLE members (
    member_id   INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT UNIQUE,
    joined_date TEXT,
    membership  TEXT DEFAULT 'standard'
);
CREATE TABLE books (
    book_id       INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    author        TEXT NOT NULL,
    genre         TEXT,
    isbn          TEXT UNIQUE,
    year_pub      INTEGER,
    copies_total  INTEGER DEFAULT 1,
    copies_avail  INTEGER DEFAULT 1
);
CREATE TABLE loans (
    loan_id     INTEGER PRIMARY KEY,
    member_id   INTEGER REFERENCES members(member_id),
    book_id     INTEGER REFERENCES books(book_id),
    loan_date   TEXT,
    due_date    TEXT,
    return_date TEXT
);

INSERT INTO members VALUES
(1,'Alice Nguyen','alice.n@mail.com','2021-01-10','premium'),
(2,'Brian Kim','brian.k@mail.com','2021-03-22','standard'),
(3,'Clara Patel','clara.p@mail.com','2021-05-14','premium'),
(4,'Derek Shaw','derek.s@mail.com','2021-07-08','standard'),
(5,'Elaine Torres','elaine.t@mail.com','2021-09-30','premium'),
(6,'Felix Chen','felix.c@mail.com','2022-01-15','standard'),
(7,'Gloria Singh','gloria.s@mail.com','2022-03-20','standard'),
(8,'Hugo Reed','hugo.r@mail.com','2022-06-11','premium'),
(9,'Ingrid Bell','ingrid.b@mail.com','2022-08-25','standard'),
(10,'Jules Mason','jules.m@mail.com','2022-11-03','premium'),
(11,'Karen Fox','karen.f@mail.com','2023-01-17','standard'),
(12,'Lars Webb','lars.w@mail.com','2023-03-29','standard'),
(13,'Maria Silva','maria.s@mail.com','2023-05-05','premium'),
(14,'Nathan Cole','nathan.c@mail.com','2023-07-19','standard'),
(15,'Olivia Hunt','olivia.h@mail.com','2023-09-22','premium'),
(16,'Pedro Ramos','pedro.r@mail.com','2023-11-04','standard'),
(17,'Quinn Adler','quinn.a@mail.com','2024-01-30','standard'),
(18,'Rosa Lim','rosa.l@mail.com','2024-03-12','premium');

INSERT INTO books VALUES
(1,'The Great Gatsby','F. Scott Fitzgerald','Fiction','9780743273565',1925,3,2),
(2,'To Kill a Mockingbird','Harper Lee','Fiction','9780061935466',1960,2,1),
(3,'1984','George Orwell','Dystopian','9780451524935',1949,4,3),
(4,'Brave New World','Aldous Huxley','Dystopian','9780060850524',1932,2,2),
(5,'The Catcher in the Rye','J.D. Salinger','Fiction','9780316769174',1951,2,0),
(6,'Sapiens','Yuval Noah Harari','Non-Fiction','9780062316097',2011,3,2),
(7,'Educated','Tara Westover','Non-Fiction','9780399590504',2018,2,1),
(8,'Atomic Habits','James Clear','Self-Help','9780735211292',2018,4,3),
(9,'Dune','Frank Herbert','Sci-Fi','9780441013593',1965,3,2),
(10,'Foundation','Isaac Asimov','Sci-Fi','9780553293357',1951,2,1),
(11,'The Hobbit','J.R.R. Tolkien','Fantasy','9780547928227',1937,5,4),
(12,'Harry Potter and the Sorcerers Stone','J.K. Rowling','Fantasy','9780439708180',1997,6,4),
(13,'The Alchemist','Paulo Coelho','Fiction','9780062315007',1988,3,3),
(14,'Thinking Fast and Slow','Daniel Kahneman','Psychology','9780374533557',2011,2,1),
(15,'Clean Code','Robert C. Martin','Technology','9780132350884',2008,3,2),
(16,'Designing Data-Intensive Applications','Martin Kleppmann','Technology','9781449373320',2017,2,1),
(17,'The Pragmatic Programmer','David Thomas','Technology','9780135957059',2019,2,2),
(18,'Pride and Prejudice','Jane Austen','Fiction','9780141439518',1813,3,3),
(19,'The Lean Startup','Eric Ries','Business','9780307887894',2011,2,2),
(20,'Deep Work','Cal Newport','Self-Help','9781455586691',2016,2,1);

INSERT INTO loans VALUES
(1,1,1,'2024-01-05','2024-01-19','2024-01-18'),
(2,2,3,'2024-01-10','2024-01-24','2024-01-25'),
(3,3,5,'2024-01-15','2024-01-29',NULL),
(4,4,8,'2024-01-20','2024-02-03','2024-02-01'),
(5,5,12,'2024-01-25','2024-02-08','2024-02-10'),
(6,6,9,'2024-02-01','2024-02-15','2024-02-14'),
(7,7,15,'2024-02-05','2024-02-19',NULL),
(8,8,6,'2024-02-10','2024-02-24','2024-02-22'),
(9,9,11,'2024-02-15','2024-03-01','2024-03-02'),
(10,10,16,'2024-02-20','2024-03-06','2024-03-05'),
(11,11,2,'2024-03-01','2024-03-15',NULL),
(12,12,7,'2024-03-05','2024-03-19','2024-03-17'),
(13,13,10,'2024-03-10','2024-03-24','2024-03-24'),
(14,14,4,'2024-03-15','2024-03-29',NULL),
(15,15,18,'2024-03-20','2024-04-03','2024-04-01'),
(16,16,14,'2024-04-01','2024-04-15','2024-04-14'),
(17,1,8,'2024-04-05','2024-04-19','2024-04-18'),
(18,2,12,'2024-04-10','2024-04-24',NULL),
(19,3,20,'2024-04-15','2024-04-29','2024-04-28'),
(20,5,3,'2024-04-20','2024-05-04','2024-05-03'),
(21,7,9,'2024-04-25','2024-05-09',NULL),
(22,9,11,'2024-05-01','2024-05-15','2024-05-14'),
(23,10,17,'2024-05-05','2024-05-19',NULL),
(24,13,5,'2024-05-10','2024-05-24',NULL),
(25,15,1,'2024-05-15','2024-05-29','2024-05-28');
""",

# ── hospital ───────────────────────────────────────────────
"hospital": """
CREATE TABLE doctors (
    doctor_id   INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    specialty   TEXT NOT NULL,
    email       TEXT UNIQUE,
    phone       TEXT,
    years_exp   INTEGER
);
CREATE TABLE patients (
    patient_id  INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    dob         TEXT,
    gender      TEXT,
    email       TEXT UNIQUE,
    phone       TEXT,
    blood_type  TEXT
);
CREATE TABLE appointments (
    appt_id     INTEGER PRIMARY KEY,
    patient_id  INTEGER REFERENCES patients(patient_id),
    doctor_id   INTEGER REFERENCES doctors(doctor_id),
    appt_date   TEXT,
    appt_time   TEXT,
    status      TEXT DEFAULT 'scheduled',
    notes       TEXT
);
CREATE TABLE prescriptions (
    rx_id           INTEGER PRIMARY KEY,
    appt_id         INTEGER REFERENCES appointments(appt_id),
    patient_id      INTEGER REFERENCES patients(patient_id),
    doctor_id       INTEGER REFERENCES doctors(doctor_id),
    drug_name       TEXT NOT NULL,
    dosage          TEXT,
    duration        TEXT,
    prescribed_date TEXT
);

INSERT INTO doctors VALUES
(1,'Dr. Sarah Chen','Cardiology','s.chen@hospital.com','555-0101',15),
(2,'Dr. Marcus Webb','Neurology','m.webb@hospital.com','555-0102',20),
(3,'Dr. Priya Patel','Pediatrics','p.patel@hospital.com','555-0103',10),
(4,'Dr. James OBrien','Orthopedics','j.obrien@hospital.com','555-0104',18),
(5,'Dr. Lisa Nakamura','Dermatology','l.nakamura@hospital.com','555-0105',12),
(6,'Dr. Carlos Ruiz','Oncology','c.ruiz@hospital.com','555-0106',22),
(7,'Dr. Emily Stone','General Practice','e.stone@hospital.com','555-0107',8),
(8,'Dr. Ahmed Hassan','Endocrinology','a.hassan@hospital.com','555-0108',14),
(9,'Dr. Rebecca Grant','Psychiatry','r.grant@hospital.com','555-0109',16),
(10,'Dr. Thomas Lee','Gastroenterology','t.lee@hospital.com','555-0110',11);

INSERT INTO patients VALUES
(1,'Michael Adams','1985-04-12','M','m.adams@mail.com','555-1001','A+'),
(2,'Jennifer Liu','1990-07-23','F','j.liu@mail.com','555-1002','O-'),
(3,'Robert Hill','1978-11-05','M','r.hill@mail.com','555-1003','B+'),
(4,'Patricia Scott','1965-02-28','F','p.scott@mail.com','555-1004','AB+'),
(5,'Christopher Young','1993-09-14','M','c.young@mail.com','555-1005','A-'),
(6,'Linda Walker','1988-06-30','F','l.walker@mail.com','555-1006','O+'),
(7,'William King','1970-12-17','M','w.king@mail.com','555-1007','B-'),
(8,'Barbara Wright','1982-03-22','F','b.wright@mail.com','555-1008','A+'),
(9,'David Green','1975-08-08','M','d.green@mail.com','555-1009','AB-'),
(10,'Susan Baker','1995-01-19','F','s.baker@mail.com','555-1010','O+'),
(11,'Daniel Nelson','1967-05-04','M','d.nelson@mail.com','555-1011','A+'),
(12,'Karen Carter','1980-10-31','F','k.carter@mail.com','555-1012','B+'),
(13,'George Mitchell','1958-07-15','M','g.mitchell@mail.com','555-1013','O-'),
(14,'Nancy Perez','1991-12-03','F','n.perez@mail.com','555-1014','A-'),
(15,'Steven Roberts','1987-04-27','M','s.roberts@mail.com','555-1015','AB+'),
(16,'Betty Turner','1972-09-09','F','b.turner@mail.com','555-1016','B+'),
(17,'Edward Phillips','1963-06-21','M','e.phillips@mail.com','555-1017','O+'),
(18,'Dorothy Campbell','1998-02-14','F','d.campbell@mail.com','555-1018','A+'),
(19,'Charles Parker','1984-11-26','M','c.parker@mail.com','555-1019','B-'),
(20,'Helen Evans','1977-08-18','F','h.evans@mail.com','555-1020','O+');

INSERT INTO appointments VALUES
(1,1,1,'2024-02-05','09:00','completed','Annual checkup'),
(2,2,3,'2024-02-06','10:30','completed','Flu symptoms'),
(3,3,4,'2024-02-07','14:00','completed','Knee pain follow-up'),
(4,4,1,'2024-02-08','11:00','completed','Hypertension review'),
(5,5,7,'2024-02-09','09:30','completed','General checkup'),
(6,6,2,'2024-02-12','13:00','completed','Migraine consultation'),
(7,7,5,'2024-02-13','15:00','completed','Rash evaluation'),
(8,8,8,'2024-02-14','10:00','completed','Diabetes management'),
(9,9,9,'2024-02-15','16:00','completed','Anxiety assessment'),
(10,10,6,'2024-02-19','11:30','completed','Cancer screening'),
(11,11,1,'2024-03-01','09:00','completed','Heart palpitations'),
(12,12,3,'2024-03-04','10:30','completed','Pediatric wellness check'),
(13,13,10,'2024-03-06','14:00','completed','Stomach issues'),
(14,14,7,'2024-03-08','09:30','completed','Cold symptoms'),
(15,15,4,'2024-03-11','15:00','completed','Back pain'),
(16,16,8,'2024-03-13','11:00','completed','Thyroid checkup'),
(17,17,2,'2024-03-15','13:30','completed','Headache investigation'),
(18,18,5,'2024-03-18','10:00','completed','Acne treatment'),
(19,19,9,'2024-03-20','16:00','scheduled','Depression follow-up'),
(20,20,1,'2024-03-22','09:00','scheduled','Chest pain investigation'),
(21,1,7,'2024-04-01','10:00','completed','Follow-up visit'),
(22,3,4,'2024-04-05','14:30','scheduled','Post-surgery review'),
(23,6,8,'2024-04-10','11:00','scheduled','Insulin adjustment'),
(24,8,1,'2024-04-15','09:30','scheduled','BP monitoring');

INSERT INTO prescriptions VALUES
(1,1,1,1,'Lisinopril','10mg daily','30 days','2024-02-05'),
(2,2,2,3,'Amoxicillin','500mg 3x/day','7 days','2024-02-06'),
(3,3,3,4,'Ibuprofen','400mg as needed','14 days','2024-02-07'),
(4,4,4,1,'Amlodipine','5mg daily','30 days','2024-02-08'),
(5,5,5,7,'Paracetamol','500mg as needed','7 days','2024-02-09'),
(6,6,6,2,'Sumatriptan','50mg as needed','30 days','2024-02-12'),
(7,7,7,5,'Hydrocortisone','apply twice daily','14 days','2024-02-13'),
(8,8,8,8,'Metformin','500mg twice daily','90 days','2024-02-14'),
(9,9,9,9,'Sertraline','50mg daily','60 days','2024-02-15'),
(10,10,10,6,'Ondansetron','8mg as needed','30 days','2024-02-19'),
(11,11,11,1,'Atenolol','25mg daily','30 days','2024-03-01'),
(12,12,12,3,'Vitamin D','1000IU daily','90 days','2024-03-04'),
(13,13,13,10,'Omeprazole','20mg daily','28 days','2024-03-06'),
(14,14,14,7,'Cetirizine','10mg daily','14 days','2024-03-08'),
(15,15,15,4,'Diclofenac','50mg twice daily','14 days','2024-03-11'),
(16,16,16,8,'Levothyroxine','50mcg daily','180 days','2024-03-13'),
(17,17,17,2,'Topiramate','25mg daily','60 days','2024-03-15'),
(18,18,18,5,'Tretinoin','apply nightly','90 days','2024-03-18'),
(19,21,1,7,'Aspirin','100mg daily','30 days','2024-04-01'),
(20,14,14,7,'Loratadine','10mg daily','30 days','2024-03-08');
""",
}

# ═══════════════════════════════════════════════════════════
# ER DIAGRAMS — text art per dataset
# ═══════════════════════════════════════════════════════════
ER_DIAGRAMS: dict[str, str] = {
"employees": """\
departments (dept_id PK, dept_name, location)
     |  1
     |  *
employees (emp_id PK, first_name, last_name, email,
           hire_date, job_title, dept_id FK, manager_id FK)
     |  1
     |  *
salaries (salary_id PK, emp_id FK, amount, from_date, to_date)
""",
"orders": """\
customers (customer_id PK, first_name, last_name,
           email, city, country, created_at)
     |  1
     |  *
orders (order_id PK, customer_id FK, order_date, status, total_amount)
     |  1
     |  *
order_items (item_id PK, order_id FK, product_id FK, quantity, unit_price)
     |  *
     |  1
products (product_id PK, product_name, category, unit_price, stock_qty)
""",
"library": """\
members (member_id PK, full_name, email, joined_date, membership)
     |  1
     |  *
loans (loan_id PK, member_id FK, book_id FK,
       loan_date, due_date, return_date)
     |  *
     |  1
books (book_id PK, title, author, genre, isbn,
       year_pub, copies_total, copies_avail)
""",
"hospital": """\
patients (patient_id PK, full_name, dob, gender, email, phone, blood_type)
    |  1                                 |  1
    |  *                                 |  *
appointments (appt_id PK,           prescriptions (rx_id PK,
  patient_id FK, doctor_id FK,        patient_id FK, doctor_id FK,
  appt_date, appt_time,               appt_id FK, drug_name,
  status, notes)                       dosage, duration, prescribed_date)
    |  *                                 |  *
    |  1                                 |  1
    +----------> doctors (doctor_id PK, full_name, specialty,
                          email, phone, years_exp)
""",
}

# ═══════════════════════════════════════════════════════════
# QUESTION BANK — 12 questions (4 MySQL + 4 SQL Server + 4 Expert)
# ═══════════════════════════════════════════════════════════
QUESTIONS: list[dict] = [

    # ── MySQL Intermediate ──────────────────────────────────
    {
        "id": 1,
        "title": "Top 5 Highest-Paid Employees",
        "dialect": "mysql",
        "difficulty": "intermediate",
        "dataset": "employees",
        "question": (
            "Find the top 5 employees with the highest **current** salary "
            "(where `to_date = '9999-01-01'`). Show full name, job title, "
            "department name, and salary amount. Order by salary descending. "
            "Use MySQL's `LIMIT` clause."
        ),
        "hint": "JOIN employees → salaries → departments. Filter WHERE to_date = '9999-01-01'. Use LIMIT 5.",
        "solution": """\
SELECT CONCAT(e.first_name, ' ', e.last_name) AS full_name,
       e.job_title,
       d.dept_name,
       s.amount AS salary
FROM employees e
JOIN salaries s ON e.emp_id = s.emp_id
JOIN departments d ON e.dept_id = d.dept_id
WHERE s.to_date = '9999-01-01'
ORDER BY s.amount DESC
LIMIT 5;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt FROM (
    SELECT e.emp_id FROM employees e
    JOIN salaries s ON e.emp_id = s.emp_id
    WHERE s.to_date = '9999-01-01'
    ORDER BY s.amount DESC LIMIT 5
) t""",
    },
    {
        "id": 2,
        "title": "Department Headcount & Avg Salary",
        "dialect": "mysql",
        "difficulty": "intermediate",
        "dataset": "employees",
        "question": (
            "For each department show: department name, employee count, and "
            "average current salary (rounded to 2 dp). Include only departments "
            "with **more than 2 employees**. Order by average salary descending. "
            "Use `IFNULL` to guard against null department names."
        ),
        "hint": "GROUP BY dept. HAVING COUNT(*) > 2. Join employees → departments → salaries (current only).",
        "solution": """\
SELECT IFNULL(d.dept_name, 'Unknown') AS dept_name,
       COUNT(e.emp_id)                AS headcount,
       ROUND(AVG(s.amount), 2)        AS avg_salary
FROM departments d
JOIN employees e ON d.dept_id = e.dept_id
JOIN salaries  s ON e.emp_id  = s.emp_id
WHERE s.to_date = '9999-01-01'
GROUP BY d.dept_id, d.dept_name
HAVING COUNT(e.emp_id) > 2
ORDER BY avg_salary DESC;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt FROM (
    SELECT d.dept_id FROM departments d
    JOIN employees e ON d.dept_id = e.dept_id
    JOIN salaries  s ON e.emp_id  = s.emp_id
    WHERE s.to_date = '9999-01-01'
    GROUP BY d.dept_id HAVING COUNT(e.emp_id) > 2
) t""",
    },
    {
        "id": 3,
        "title": "Revenue by Product Category",
        "dialect": "mysql",
        "difficulty": "intermediate",
        "dataset": "orders",
        "question": (
            "Calculate total revenue per product category for **completed** orders. "
            "Show category and total revenue (rounded to 2 dp), ordered by revenue desc. "
            "Use `IFNULL` to replace any NULL category with `'Uncategorized'`."
        ),
        "hint": "Join order_items → products → orders. Filter WHERE status = 'completed'. SUM(quantity * unit_price).",
        "solution": """\
SELECT IFNULL(p.category, 'Uncategorized') AS category,
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders   o ON oi.order_id   = o.order_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY total_revenue DESC;""",
        "expected_check": """\
SELECT COUNT(DISTINCT IFNULL(p.category,'Uncategorized')) AS cnt
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status = 'completed'""",
    },
    {
        "id": 4,
        "title": "Overdue Library Loans",
        "dialect": "mysql",
        "difficulty": "intermediate",
        "dataset": "library",
        "question": (
            "Find all loans **returned late** (return_date > due_date). "
            "Show member name, book title, due date, return date, and days overdue. "
            "Use MySQL's `DATEDIFF(return_date, due_date)`. Order by days overdue desc."
        ),
        "hint": "Filter WHERE return_date > due_date AND return_date IS NOT NULL. DATEDIFF(return_date, due_date) for days.",
        "solution": """\
SELECT m.full_name                          AS member,
       b.title                             AS book,
       l.due_date,
       l.return_date,
       DATEDIFF(l.return_date, l.due_date) AS days_overdue
FROM loans l
JOIN members m ON l.member_id = m.member_id
JOIN books   b ON l.book_id   = b.book_id
WHERE l.return_date > l.due_date
ORDER BY days_overdue DESC;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt
FROM loans
WHERE return_date IS NOT NULL AND return_date > due_date""",
    },

    # ── SQL Server Intermediate ─────────────────────────────
    {
        "id": 5,
        "title": "Top 3 Customers by Order Count",
        "dialect": "sqlserver",
        "difficulty": "intermediate",
        "dataset": "orders",
        "question": (
            "Using `SELECT TOP 3`, find the customers with the most orders. "
            "Show concatenated full name (using `+`), city, country, and order count. "
            "Use `ISNULL` to replace NULL city with `'Unknown'`."
        ),
        "hint": "SELECT TOP 3. Concatenate with +. Join customers → orders. GROUP BY customer.",
        "solution": """\
SELECT TOP 3
    ISNULL(c.first_name, '') + ' ' + ISNULL(c.last_name, '') AS full_name,
    ISNULL(c.city, 'Unknown')                                 AS city,
    c.country,
    COUNT(o.order_id)                                         AS order_count
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name, c.city, c.country
ORDER BY order_count DESC;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt FROM (
    SELECT c.customer_id FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_id ORDER BY COUNT(o.order_id) DESC LIMIT 3
) t""",
    },
    {
        "id": 6,
        "title": "Doctors with Most Completed Appointments",
        "dialect": "sqlserver",
        "difficulty": "intermediate",
        "dataset": "hospital",
        "question": (
            "Find the **top 5** doctors by completed appointments. "
            "Show doctor name, specialty, character length of specialty using `LEN()`, "
            "and appointment count. Use `SELECT TOP 5`."
        ),
        "hint": "SELECT TOP 5. Filter appointments WHERE status = 'completed'. LEN(specialty) for length.",
        "solution": """\
SELECT TOP 5
    d.full_name,
    d.specialty,
    LEN(d.specialty)  AS specialty_len,
    COUNT(a.appt_id)  AS appt_count
FROM doctors d
JOIN appointments a ON d.doctor_id = a.doctor_id
WHERE a.status = 'completed'
GROUP BY d.doctor_id, d.full_name, d.specialty
ORDER BY appt_count DESC;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt FROM (
    SELECT d.doctor_id FROM doctors d
    JOIN appointments a ON d.doctor_id = a.doctor_id
    WHERE a.status = 'completed'
    GROUP BY d.doctor_id ORDER BY COUNT(*) DESC LIMIT 5
) t""",
    },
    {
        "id": 7,
        "title": "Products Never Ordered",
        "dialect": "sqlserver",
        "difficulty": "intermediate",
        "dataset": "orders",
        "question": (
            "Using a **NOT IN subquery**, find all products never ordered. "
            "Show product name, category (`ISNULL` → `'N/A'`), and unit price. "
            "Order alphabetically by product name."
        ),
        "hint": "WHERE product_id NOT IN (SELECT DISTINCT product_id FROM order_items).",
        "solution": """\
SELECT product_name,
       ISNULL(category, 'N/A') AS category,
       unit_price
FROM products
WHERE product_id NOT IN (
    SELECT DISTINCT product_id FROM order_items
)
ORDER BY product_name;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt
FROM products
WHERE product_id NOT IN (SELECT DISTINCT product_id FROM order_items)""",
    },
    {
        "id": 8,
        "title": "Patient Prescriptions with STRING_AGG",
        "dialect": "sqlserver",
        "difficulty": "intermediate",
        "dataset": "hospital",
        "question": (
            "For each patient with **at least 2 prescriptions**, show: full name, "
            "blood type, prescription count, and all drug names using "
            "`STRING_AGG(drug_name, ', ')`. Order by prescription count desc."
        ),
        "hint": "STRING_AGG(drug_name, ', '). Join patients → prescriptions. HAVING COUNT >= 2.",
        "solution": """\
SELECT p.full_name,
       p.blood_type,
       COUNT(rx.rx_id)                AS prescription_count,
       STRING_AGG(rx.drug_name, ', ') AS drugs_prescribed
FROM patients p
JOIN prescriptions rx ON p.patient_id = rx.patient_id
GROUP BY p.patient_id, p.full_name, p.blood_type
HAVING COUNT(rx.rx_id) >= 2
ORDER BY prescription_count DESC;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt FROM (
    SELECT patient_id FROM prescriptions
    GROUP BY patient_id HAVING COUNT(*) >= 2
) t""",
    },

    # ── Expert / Both Dialects ──────────────────────────────
    {
        "id": 9,
        "title": "Salary Ranking with Window Functions",
        "dialect": "both",
        "difficulty": "expert",
        "dataset": "employees",
        "question": (
            "Using window functions, rank employees **within each department** by current salary. "
            "Show: dept name, full name, salary, `RANK()` and `DENSE_RANK()` within dept. "
            "Filter: `to_date = '9999-01-01'`. Order by dept name then rank."
        ),
        "hint": "RANK() OVER (PARTITION BY d.dept_id ORDER BY s.amount DESC). Same pattern for DENSE_RANK().",
        "solution": """\
SELECT d.dept_name,
       e.first_name || ' ' || e.last_name                               AS full_name,
       s.amount                                                          AS salary,
       RANK()       OVER (PARTITION BY d.dept_id ORDER BY s.amount DESC) AS dept_rank,
       DENSE_RANK() OVER (PARTITION BY d.dept_id ORDER BY s.amount DESC) AS dense_rank
FROM employees e
JOIN departments d ON e.dept_id = d.dept_id
JOIN salaries    s ON e.emp_id  = s.emp_id
WHERE s.to_date = '9999-01-01'
ORDER BY d.dept_name, dept_rank;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt
FROM employees e
JOIN salaries s ON e.emp_id = s.emp_id
WHERE s.to_date = '9999-01-01'""",
    },
    {
        "id": 10,
        "title": "Running Total Revenue (CTE + Window)",
        "dialect": "both",
        "difficulty": "expert",
        "dataset": "orders",
        "question": (
            "Using a **CTE**, compute monthly revenue from completed orders "
            "(month as `YYYY-MM`). Add a **running total** column with "
            "`SUM() OVER (ORDER BY month ROWS UNBOUNDED PRECEDING)`. "
            "Show: month, monthly_revenue, cumulative_revenue."
        ),
        "hint": "CTE: GROUP BY SUBSTR(order_date,1,7). Then SUM(revenue) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING).",
        "solution": """\
WITH monthly_revenue AS (
    SELECT SUBSTR(o.order_date, 1, 7)      AS month,
           SUM(oi.quantity * oi.unit_price) AS revenue
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.status = 'completed'
    GROUP BY SUBSTR(o.order_date, 1, 7)
)
SELECT month,
       ROUND(revenue, 2) AS monthly_revenue,
       ROUND(SUM(revenue) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING), 2) AS cumulative_revenue
FROM monthly_revenue
ORDER BY month;""",
        "expected_check": """\
SELECT COUNT(DISTINCT SUBSTR(order_date,1,7)) AS cnt
FROM orders WHERE status = 'completed'""",
    },
    {
        "id": 11,
        "title": "Above-Average Borrowers (Correlated Subquery)",
        "dialect": "both",
        "difficulty": "expert",
        "dataset": "library",
        "question": (
            "Using a **correlated subquery** in the HAVING clause, find members "
            "who borrowed more books than the average borrows per member. "
            "Show: name, membership tier, loan count, and overall average (2 dp). "
            "Order by loan count desc."
        ),
        "hint": "HAVING COUNT(l.loan_id) > (SELECT AVG(cnt) FROM (SELECT COUNT(*) AS cnt FROM loans GROUP BY member_id) t).",
        "solution": """\
SELECT m.full_name,
       m.membership,
       COUNT(l.loan_id) AS loan_count,
       ROUND(
           (SELECT AVG(cnt) FROM (
               SELECT COUNT(loan_id) AS cnt FROM loans GROUP BY member_id
           ) sub),
       2) AS avg_loans
FROM members m
JOIN loans l ON m.member_id = l.member_id
GROUP BY m.member_id, m.full_name, m.membership
HAVING COUNT(l.loan_id) > (
    SELECT AVG(cnt) FROM (
        SELECT COUNT(loan_id) AS cnt FROM loans GROUP BY member_id
    ) sub
)
ORDER BY loan_count DESC;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt FROM (
    SELECT member_id FROM loans GROUP BY member_id
    HAVING COUNT(*) > (
        SELECT AVG(cnt) FROM (SELECT COUNT(*) AS cnt FROM loans GROUP BY member_id) t
    )
) x""",
    },
    {
        "id": 12,
        "title": "Doctor Patient Journey (Multi-CTE + RANK)",
        "dialect": "both",
        "difficulty": "expert",
        "dataset": "hospital",
        "question": (
            "Using **two CTEs**, compute per-doctor: unique patient count and prescription count. "
            "Join to doctors, add `RANK() OVER (ORDER BY unique_patients DESC)`. "
            "Include only doctors with **> 2 unique patients**. "
            "Show: name, specialty, years_exp, unique_patients, prescriptions_written, patient_rank."
        ),
        "hint": "CTE 1: COUNT(DISTINCT patient_id) from appointments. CTE 2: COUNT(rx_id) from prescriptions. LEFT JOIN both to doctors.",
        "solution": """\
WITH patient_counts AS (
    SELECT doctor_id,
           COUNT(DISTINCT patient_id) AS unique_patients
    FROM appointments
    GROUP BY doctor_id
),
rx_counts AS (
    SELECT doctor_id,
           COUNT(rx_id) AS prescriptions_written
    FROM prescriptions
    GROUP BY doctor_id
)
SELECT d.full_name,
       d.specialty,
       d.years_exp,
       COALESCE(pc.unique_patients,       0) AS unique_patients,
       COALESCE(rc.prescriptions_written,  0) AS prescriptions_written,
       RANK() OVER (ORDER BY COALESCE(pc.unique_patients, 0) DESC) AS patient_rank
FROM doctors d
LEFT JOIN patient_counts pc ON d.doctor_id = pc.doctor_id
LEFT JOIN rx_counts      rc ON d.doctor_id = rc.doctor_id
WHERE COALESCE(pc.unique_patients, 0) > 2
ORDER BY patient_rank;""",
        "expected_check": """\
SELECT COUNT(*) AS cnt FROM (
    SELECT doctor_id FROM appointments
    GROUP BY doctor_id HAVING COUNT(DISTINCT patient_id) > 2
) t""",
    },
]

# ── Skeleton templates (structure without the answer) ──────
SKELETONS: dict[int, str] = {
    1: (
        "-- Q1: Top 5 highest-paid employees (MySQL)\n"
        "-- Hint: JOIN employees → salaries → departments\n"
        "-- Filter current salaries: WHERE to_date = '9999-01-01'\n\n"
        "SELECT -- full_name, job_title, dept_name, salary\n"
        "FROM employees e\n"
        "JOIN -- add salaries join\n"
        "JOIN -- add departments join\n"
        "WHERE -- current salary filter\n"
        "ORDER BY -- salary desc\n"
        "LIMIT 5;"
    ),
    2: (
        "-- Q2: Department headcount & avg salary (MySQL)\n"
        "-- Hint: GROUP BY dept, HAVING COUNT > 2\n\n"
        "SELECT IFNULL(d.dept_name, 'Unknown') AS dept_name,\n"
        "       -- headcount,\n"
        "       -- avg salary\n"
        "FROM departments d\n"
        "JOIN -- employees\n"
        "JOIN -- salaries (current)\n"
        "WHERE -- filter\n"
        "GROUP BY d.dept_id, d.dept_name\n"
        "HAVING -- condition\n"
        "ORDER BY avg_salary DESC;"
    ),
    3: (
        "-- Q3: Revenue by product category (MySQL)\n"
        "-- Hint: SUM(quantity * unit_price), filter completed orders\n\n"
        "SELECT IFNULL(p.category, 'Uncategorized') AS category,\n"
        "       ROUND(SUM(/* oi.quantity * oi.unit_price */), 2) AS total_revenue\n"
        "FROM order_items oi\n"
        "JOIN -- products\n"
        "JOIN -- orders\n"
        "WHERE -- status = 'completed'\n"
        "GROUP BY p.category\n"
        "ORDER BY total_revenue DESC;"
    ),
    4: (
        "-- Q4: Overdue library loans (MySQL)\n"
        "-- Hint: return_date > due_date, DATEDIFF for days\n\n"
        "SELECT m.full_name AS member,\n"
        "       b.title     AS book,\n"
        "       l.due_date,\n"
        "       l.return_date,\n"
        "       DATEDIFF(/* end, start */) AS days_overdue\n"
        "FROM loans l\n"
        "JOIN -- members\n"
        "JOIN -- books\n"
        "WHERE -- overdue condition\n"
        "ORDER BY days_overdue DESC;"
    ),
    5: (
        "-- Q5: Top 3 customers by order count (SQL Server)\n"
        "-- Hint: SELECT TOP 3, concatenate with +, ISNULL\n\n"
        "SELECT TOP 3\n"
        "    ISNULL(c.first_name,'') + ' ' + ISNULL(c.last_name,'') AS full_name,\n"
        "    ISNULL(c.city, 'Unknown') AS city,\n"
        "    c.country,\n"
        "    COUNT(/* orders */) AS order_count\n"
        "FROM customers c\n"
        "JOIN orders o ON c.customer_id = o.customer_id\n"
        "GROUP BY c.customer_id, c.first_name, c.last_name, c.city, c.country\n"
        "ORDER BY order_count DESC;"
    ),
    6: (
        "-- Q6: Top 5 doctors by completed appointments (SQL Server)\n"
        "-- Hint: SELECT TOP 5, LEN() for string length\n\n"
        "SELECT TOP 5\n"
        "    d.full_name,\n"
        "    d.specialty,\n"
        "    LEN(d.specialty) AS specialty_len,\n"
        "    COUNT(/* appts */) AS appt_count\n"
        "FROM doctors d\n"
        "JOIN appointments a ON d.doctor_id = a.doctor_id\n"
        "WHERE a.status = 'completed'\n"
        "GROUP BY d.doctor_id, d.full_name, d.specialty\n"
        "ORDER BY appt_count DESC;"
    ),
    7: (
        "-- Q7: Products never ordered (SQL Server)\n"
        "-- Hint: NOT IN subquery on order_items\n\n"
        "SELECT product_name,\n"
        "       ISNULL(category, 'N/A') AS category,\n"
        "       unit_price\n"
        "FROM products\n"
        "WHERE product_id NOT IN (\n"
        "    SELECT DISTINCT /* column */ FROM order_items\n"
        ")\n"
        "ORDER BY product_name;"
    ),
    8: (
        "-- Q8: Patient prescriptions with STRING_AGG (SQL Server)\n"
        "-- Hint: STRING_AGG(drug_name, ', '), HAVING COUNT >= 2\n\n"
        "SELECT p.full_name,\n"
        "       p.blood_type,\n"
        "       COUNT(rx.rx_id)               AS prescription_count,\n"
        "       STRING_AGG(rx.drug_name, ', ') AS drugs_prescribed\n"
        "FROM patients p\n"
        "JOIN prescriptions rx ON p.patient_id = rx.patient_id\n"
        "GROUP BY p.patient_id, p.full_name, p.blood_type\n"
        "HAVING /* count condition */\n"
        "ORDER BY prescription_count DESC;"
    ),
    9: (
        "-- Q9: Salary ranking with window functions\n"
        "-- Hint: RANK() OVER (PARTITION BY dept ORDER BY salary DESC)\n\n"
        "SELECT d.dept_name,\n"
        "       e.first_name || ' ' || e.last_name AS full_name,\n"
        "       s.amount AS salary,\n"
        "       RANK()       OVER (PARTITION BY /* ... */ ORDER BY /* ... */) AS dept_rank,\n"
        "       DENSE_RANK() OVER (PARTITION BY /* ... */ ORDER BY /* ... */) AS dense_rank\n"
        "FROM employees e\n"
        "JOIN -- departments\n"
        "JOIN -- salaries\n"
        "WHERE -- current salary\n"
        "ORDER BY d.dept_name, dept_rank;"
    ),
    10: (
        "-- Q10: Running total revenue (CTE + Window)\n"
        "-- Hint: SUM() OVER (ORDER BY month ROWS UNBOUNDED PRECEDING)\n\n"
        "WITH monthly_revenue AS (\n"
        "    SELECT SUBSTR(o.order_date, 1, 7) AS month,\n"
        "           SUM(/* revenue */) AS revenue\n"
        "    FROM orders o\n"
        "    JOIN order_items oi ON o.order_id = oi.order_id\n"
        "    WHERE /* filter */\n"
        "    GROUP BY /* month */\n"
        ")\n"
        "SELECT month,\n"
        "       ROUND(revenue, 2) AS monthly_revenue,\n"
        "       ROUND(SUM(revenue) OVER (ORDER BY month ROWS UNBOUNDED PRECEDING), 2) AS cumulative_revenue\n"
        "FROM monthly_revenue\n"
        "ORDER BY month;"
    ),
    11: (
        "-- Q11: Above-average borrowers (correlated subquery)\n"
        "-- Hint: HAVING COUNT > (SELECT AVG(cnt) FROM (... GROUP BY member_id) t)\n\n"
        "SELECT m.full_name, m.membership,\n"
        "       COUNT(l.loan_id) AS loan_count,\n"
        "       ROUND((SELECT AVG(cnt) FROM (\n"
        "           SELECT COUNT(loan_id) AS cnt FROM loans GROUP BY member_id\n"
        "       ) sub), 2) AS avg_loans\n"
        "FROM members m\n"
        "JOIN loans l ON m.member_id = l.member_id\n"
        "GROUP BY m.member_id, m.full_name, m.membership\n"
        "HAVING COUNT(l.loan_id) > (\n"
        "    /* correlated scalar subquery */\n"
        ")\n"
        "ORDER BY loan_count DESC;"
    ),
    12: (
        "-- Q12: Doctor patient journey (Multi-CTE + RANK)\n"
        "-- Hint: CTE1 = patient counts, CTE2 = rx counts, then RANK()\n\n"
        "WITH patient_counts AS (\n"
        "    SELECT doctor_id,\n"
        "           COUNT(DISTINCT patient_id) AS unique_patients\n"
        "    FROM appointments\n"
        "    GROUP BY doctor_id\n"
        "),\n"
        "rx_counts AS (\n"
        "    SELECT doctor_id,\n"
        "           COUNT(rx_id) AS prescriptions_written\n"
        "    FROM prescriptions\n"
        "    GROUP BY doctor_id\n"
        ")\n"
        "SELECT d.full_name, d.specialty, d.years_exp,\n"
        "       COALESCE(pc.unique_patients, 0)      AS unique_patients,\n"
        "       COALESCE(rc.prescriptions_written, 0) AS prescriptions_written,\n"
        "       RANK() OVER (ORDER BY COALESCE(pc.unique_patients,0) DESC) AS patient_rank\n"
        "FROM doctors d\n"
        "LEFT JOIN patient_counts pc ON d.doctor_id = pc.doctor_id\n"
        "LEFT JOIN rx_counts      rc ON d.doctor_id = rc.doctor_id\n"
        "WHERE COALESCE(pc.unique_patients, 0) > 2\n"
        "ORDER BY patient_rank;"
    ),
}

# ═══════════════════════════════════════════════════════════
# SYNTAX CHEAT SHEET
# ═══════════════════════════════════════════════════════════
CHEAT_SHEET: list[tuple[str, str, str]] = [
    ("Limit rows",         "SELECT ... LIMIT 10",                   "SELECT TOP 10 ..."),
    ("Limit + offset",     "LIMIT 10 OFFSET 20",                    "OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY"),
    ("Null coalesce",      "IFNULL(col, 'default')",                "ISNULL(col, 'default')"),
    ("Auto increment",     "col INT AUTO_INCREMENT",                "col INT IDENTITY(1,1)"),
    ("String length",      "CHAR_LENGTH(str) / LENGTH(str)",        "LEN(str)"),
    ("Find in string",     "LOCATE(substr, str)",                   "CHARINDEX(substr, str)"),
    ("String concat",      "CONCAT(a, b)  or  a || b",             "a + b  or  CONCAT(a, b)"),
    ("Current datetime",   "NOW() / CURRENT_TIMESTAMP",             "GETDATE() / CURRENT_TIMESTAMP"),
    ("Format date",        "DATE_FORMAT(d, '%Y-%m-%d')",            "FORMAT(d, 'yyyy-MM-dd')"),
    ("Aggregate strings",  "GROUP_CONCAT(col SEPARATOR ',')",       "STRING_AGG(col, ',')"),
    ("Conditional",        "IF(cond, a, b)  or  CASE WHEN",         "IIF(cond, a, b)  or  CASE WHEN"),
    ("Substring",          "SUBSTRING(str, pos, len)",              "SUBSTRING(str, pos, len)"),
    ("Date difference",    "DATEDIFF(end_date, start_date) → days", "DATEDIFF(day, start, end) → days"),
    ("Add to date",        "DATE_ADD(d, INTERVAL 7 DAY)",           "DATEADD(day, 7, d)"),
    ("Pagination",         "LIMIT 10 OFFSET 30",                    "OFFSET 30 ROWS FETCH NEXT 10 ROWS ONLY"),
    ("Temp tables",        "CREATE TEMPORARY TABLE t (...)",        "SELECT ... INTO #temp_name"),
    ("Cast type",          "CAST(col AS CHAR)",                     "CAST(col AS VARCHAR(100))"),
    ("Comments",           "-- line  or  /* block */",              "-- line  or  /* block */"),
]


# ═══════════════════════════════════════════════════════════
# DATABASE FUNCTIONS
# ═══════════════════════════════════════════════════════════

def init_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database and seed all four schemas."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for name, ddl in SCHEMA_SQL.items():
        try:
            conn.executescript(ddl)
        except Exception as exc:
            st.error(f"DB init error for '{name}': {exc}")
    conn.commit()
    return conn


def get_tables(dataset: str) -> list[str]:
    return ALL_TABLES.get(dataset, [])


def get_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [{"name": r["name"], "type": r["type"] or "TEXT", "pk": bool(r["pk"])}
                for r in cur.fetchall()]
    except Exception:
        return []


def preview_table(conn: sqlite3.Connection, table: str) -> tuple[list[str], list[list]]:
    try:
        cur = conn.execute(f"SELECT * FROM {table} LIMIT 5")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [list(r) for r in rows]
    except Exception:
        return [], []


# ═══════════════════════════════════════════════════════════
# TRANSLATION LAYER
# ═══════════════════════════════════════════════════════════

def _split_args(s: str) -> list[str]:
    """Split function arguments respecting nested parentheses."""
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "," and depth == 0:
            parts.append("".join(cur)); cur = []
        else:
            depth += ch == "("
            depth -= ch == ")"
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def _mysql_fmt_to_strftime(fmt: str) -> str:
    for m, s in {"%Y":"%Y","%y":"%y","%m":"%m","%d":"%d",
                 "%H":"%H","%i":"%M","%s":"%S"}.items():
        fmt = fmt.replace(m, s)
    return fmt


def preprocess_sql(sql: str, dialect: str) -> tuple[str, str | None, bool]:
    """
    Intercept dialect commands sqlglot cannot handle.
    Returns (processed_sql, warning_or_None, was_fully_intercepted).
    """
    s = sql.strip()

    if dialect == "mysql" and re.match(r"^\s*SHOW\s+TABLES\s*;?\s*$", s, re.I):
        return "SELECT name AS 'Tables' FROM sqlite_master WHERE type='table' ORDER BY name;", None, True

    m = re.match(r"^\s*(?:DESCRIBE|DESC)\s+(\w+)\s*;?\s*$", s, re.I)
    if m and dialect == "mysql":
        return f"PRAGMA table_info({m.group(1)});", None, True

    if dialect == "sqlserver" and re.search(r"\bINTO\s+#\w+", s, re.I):
        return "__TEMP__", (
            "Temporary tables (#temp) are not supported in the sandbox. "
            "Rewrite using a CTE:  WITH cte AS (SELECT ...) SELECT ... FROM cte"
        ), True

    warning = None
    if dialect == "mysql" and re.search(r"\bDATE_FORMAT\s*\(", s, re.I):
        warning = "DATE_FORMAT() approximated with SQLite strftime() — minor format differences possible."
        def _sub(m: re.Match) -> str:
            parts = _split_args(m.group(1))
            if len(parts) >= 2:
                col = parts[0].strip()
                fmt = parts[1].strip().strip("'\"")
                return f"strftime('{_mysql_fmt_to_strftime(fmt)}', {col})"
            return m.group(0)
        s = re.sub(r"\bDATE_FORMAT\s*\(([^)]+)\)", _sub, s, flags=re.I)

    return s, warning, False


def postprocess_sql(sql: str, dialect: str) -> str:
    """Apply post-transpile fixups for patterns sqlglot may miss."""
    if dialect == "mysql":
        sql = re.sub(r"\bNOW\s*\(\s*\)", "DATETIME('now')", sql, flags=re.I)

        def _datediff(m: re.Match) -> str:
            parts = _split_args(m.group(1))
            if len(parts) == 2:
                return f"CAST(JULIANDAY({parts[0].strip()}) - JULIANDAY({parts[1].strip()}) AS INTEGER)"
            return m.group(0)
        sql = re.sub(r"\bDATEDIFF\s*\(([^)]+)\)", _datediff, sql, flags=re.I)

    if dialect == "sqlserver":
        sql = re.sub(r"\bGETDATE\s*\(\s*\)", "DATETIME('now')", sql, flags=re.I)
        sql = re.sub(r"\bLEN\s*\(", "LENGTH(", sql, flags=re.I)
        sql = re.sub(r"\bISNULL\s*\(", "IFNULL(", sql, flags=re.I)
        sql = re.sub(r"\bSTRING_AGG\s*\(", "GROUP_CONCAT(", sql, flags=re.I)

        def _charindex(m: re.Match) -> str:
            parts = _split_args(m.group(1))
            if len(parts) >= 2:
                return f"INSTR({parts[1].strip()}, {parts[0].strip()})"
            return m.group(0)
        sql = re.sub(r"\bCHARINDEX\s*\(([^)]+)\)", _charindex, sql, flags=re.I)

    return sql


def translate_query(sql: str, dialect: str) -> tuple[str, str | None, str | None]:
    """
    Full pipeline: preprocess → sqlglot transpile → postprocess.
    Returns (translated_sql, warning, error).
    """
    preprocessed, warning, intercepted = preprocess_sql(sql, dialect)
    if preprocessed == "__TEMP__":
        return "__TEMP__", warning, None

    read_map = {"mysql": "mysql", "sqlserver": "tsql"}
    try:
        stmts = sqlglot.transpile(
            preprocessed,
            read=read_map.get(dialect, "mysql"),
            write="sqlite",
            error_level=sqlglot.ErrorLevel.RAISE,
        )
        translated = ";\n".join(s for s in stmts if s) or preprocessed
    except sqlglot_errors.SqlglotError as exc:
        label = "MySQL" if dialect == "mysql" else "SQL Server"
        return preprocessed, warning, f"Parse error ({label}): {exc}"
    except Exception as exc:
        return preprocessed, warning, f"Translation error: {exc}"

    return postprocess_sql(translated, dialect), warning, None


# ═══════════════════════════════════════════════════════════
# QUERY EXECUTION
# ═══════════════════════════════════════════════════════════

_DML = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "REPLACE")


def run_query(conn: sqlite3.Connection, sql: str, dialect: str) -> dict:
    """Translate and execute SQL. Returns a result dict."""
    result = dict(
        success=False, columns=[], rows=[], rowcount=0,
        elapsed_ms=0.0, is_dml=False, empty=False,
        error=None, warning=None, translated_sql="",
        intercepted_temp=False,
    )

    translated, warning, err = translate_query(sql, dialect)
    result["warning"] = warning
    result["translated_sql"] = translated

    if translated == "__TEMP__":
        result["intercepted_temp"] = True
        result["success"] = True
        return result

    if err:
        result["error"] = err
        return result

    is_dml = any(translated.strip().upper().startswith(k) for k in _DML)
    result["is_dml"] = is_dml

    t0 = time.perf_counter()
    try:
        stmts = [s.strip() for s in translated.split(";") if s.strip()]
        last = conn.cursor()
        for stmt in stmts:
            last = conn.execute(stmt)
        if is_dml:
            conn.commit()
            result["rowcount"] = last.rowcount if last.rowcount >= 0 else 0
        else:
            rows = last.fetchall()
            cols = [d[0] for d in last.description] if last.description else []
            result["columns"] = cols
            result["rows"] = [list(r) for r in rows]
            result["rowcount"] = len(rows)
            result["empty"] = len(rows) == 0
        result["success"] = True
    except sqlite3.Error as exc:
        result["error"] = _friendly_error(str(exc), dialect, sql)
    except Exception as exc:
        result["error"] = f"Unexpected error: {exc}"
    finally:
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return result


def _friendly_error(err: str, dialect: str, sql: str) -> str:
    e = err.lower()
    label = "MySQL" if dialect == "mysql" else "SQL Server"
    all_tables = [t for ts in ALL_TABLES.values() for t in ts]

    if "no such table" in e:
        m = re.search(r"no such table:\s*(\S+)", err, re.I)
        t = m.group(1) if m else "?"
        return (f"Table '{t}' not found. Available: {', '.join(sorted(all_tables))}. "
                f"Check the Dataset selector in the sidebar.")
    if "no such column" in e:
        m = re.search(r"no such column:\s*(\S+)", err, re.I)
        col = m.group(1) if m else "?"
        return (f"Column '{col}' not found. Use the Schema Explorer to verify column names.")
    if "syntax error" in e:
        tip = ""
        u = sql.strip().upper()
        if "SELECT" in u and "FROM" not in u:
            tip = " Tip: missing FROM clause?"
        elif not sql.strip().endswith(";"):
            tip = " Tip: try adding a semicolon at the end."
        return f"{label} syntax error.{tip}  Detail: {err}"
    if "ambiguous column" in e:
        m = re.search(r"ambiguous column name:\s*(\S+)", err, re.I)
        col = m.group(1) if m else "?"
        return f"Ambiguous column '{col}'. Qualify with a table alias, e.g. e.{col}."
    if "unique constraint" in e:
        return f"Unique constraint violation — value already exists. Detail: {err}"
    return f"Execution error ({label}): {err}"


# ═══════════════════════════════════════════════════════════
# ANSWER CHECKER
# ═══════════════════════════════════════════════════════════

def check_answer(conn: sqlite3.Connection, user_sql: str,
                 question: dict, dialect: str) -> dict:
    user = run_query(conn, user_sql, dialect)
    if not user["success"] or user.get("error"):
        return dict(passed=False, user_rowcount=0, expected_rowcount=None,
                    message=f"Your query failed: {user.get('error','unknown error')}")

    val = run_query(conn, question["expected_check"], "mysql")
    if not val["success"]:
        return dict(passed=False, user_rowcount=user["rowcount"], expected_rowcount=None,
                    message=f"Validation failed: {val.get('error')}")

    expected = int(val["rows"][0][0]) if val["rows"] else 0
    got = user["rowcount"]
    if got == expected:
        return dict(passed=True, user_rowcount=got, expected_rowcount=expected,
                    message=f"Correct! Your query returned {got} row(s) as expected.")
    return dict(passed=False, user_rowcount=got, expected_rowcount=expected,
                message=(f"Not quite. Expected {expected} row(s), got {got}. "
                         f"Re-check your WHERE / HAVING / JOIN conditions."))


# ═══════════════════════════════════════════════════════════
# HISTORY HELPERS
# ═══════════════════════════════════════════════════════════

def add_to_history(sql: str, rowcount: int) -> None:
    if SK_HISTORY not in st.session_state:
        st.session_state[SK_HISTORY] = []
    st.session_state[SK_HISTORY] = (
        [{"timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
          "sql": sql, "rows": rowcount}]
        + st.session_state[SK_HISTORY]
    )[:MAX_HISTORY]


def load_into_editor(sql: str) -> None:
    st.session_state[SK_EDITOR_SQL] = sql
    st.session_state[SK_EDITOR_KEY] = st.session_state.get(SK_EDITOR_KEY, 0) + 1


# ═══════════════════════════════════════════════════════════
# BADGE HELPERS
# ═══════════════════════════════════════════════════════════

def _diff_badge(d: str) -> str:
    return "🟡 Intermediate" if d == "intermediate" else "🔴 Expert"

def _dialect_badge(d: str) -> str:
    return {"mysql":"🐬 MySQL","sqlserver":"🪟 SQL Server","both":"🌐 Both"}.get(d, d)

def _dataset_badge(d: str) -> str:
    icons = {"employees":"👥","orders":"🛒","library":"📚","hospital":"🏥"}
    return f"{icons.get(d,'🗃️')} {d.capitalize()}"


# ═══════════════════════════════════════════════════════════
# UI COMPONENTS
# ═══════════════════════════════════════════════════════════

def render_schema_explorer(conn: sqlite3.Connection, dataset: str) -> None:
    with st.sidebar.expander("🗂️ Schema Explorer", expanded=False):
        for table in get_tables(dataset):
            with st.expander(f"📋 {table}", expanded=False):
                for col in get_columns(conn, table):
                    pk = " 🔑" if col["pk"] else ""
                    st.markdown(f"- `{col['name']}` *{col['type']}*{pk}")
                if st.button(f"Preview {table}", key=f"prev_{table}_{dataset}"):
                    pcols, prows = preview_table(conn, table)
                    if prows:
                        st.dataframe(pd.DataFrame(prows, columns=pcols),
                                     width='stretch', hide_index=True)
                    else:
                        st.info("Table is empty.")


def render_syntax_reference(dialect: str) -> None:
    with st.sidebar.expander("📖 Syntax Reference", expanded=False):
        st.caption(f"Active: **{'MySQL' if dialect=='mysql' else 'SQL Server'}**")
        for feature, mysql_s, ss_s in CHEAT_SHEET:
            st.markdown(f"**{feature}**")
            c1, c2 = st.columns(2)
            with c1:
                st.caption("MySQL"); st.code(mysql_s, language="sql")
            with c2:
                st.caption("SQL Server"); st.code(ss_s, language="sql")


def render_query_history() -> None:
    history: list = st.session_state.get(SK_HISTORY, [])
    with st.sidebar.expander(f"🕐 Query History ({len(history)})", expanded=False):
        if not history:
            st.caption("No queries yet.")
            return
        for i, e in enumerate(history):
            preview = e["sql"][:60] + ("…" if len(e["sql"]) > 60 else "")
            st.markdown(f"**{e['timestamp']}** — {e['rows']} row(s)")
            st.caption(f"`{preview}`")
            if st.button("↩ Reload", key=f"hist_{i}"):
                load_into_editor(e["sql"])
                st.rerun()
            st.markdown("---")


def render_results(result: dict) -> None:
    if result.get("intercepted_temp"):
        st.warning(f"⚠️ {result.get('warning')}")
        return
    if result.get("warning"):
        st.warning(f"⚠️ {result['warning']}")
    if result.get("error"):
        st.error(f"❌ {result['error']}")
        return
    if result["is_dml"]:
        st.success(f"✅ Statement executed — {result['rowcount']} row(s) affected "
                   f"in {result['elapsed_ms']} ms.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows returned", result["rowcount"])
    c2.metric("Columns", len(result["columns"]))
    c3.metric("Time (ms)", result["elapsed_ms"])
    if result["empty"]:
        st.info("ℹ️ Query ran successfully but returned 0 rows. "
                "Check your WHERE / JOIN conditions.")
        return
    if result["rows"] and result["columns"]:
        st.dataframe(pd.DataFrame(result["rows"], columns=result["columns"]),
                     width='stretch', hide_index=True)


def render_sql_editor(dialect: str, dataset: str) -> str:
    samples = {
        "mysql":     f"-- MySQL\nSELECT *\nFROM {get_tables(dataset)[0]}\nLIMIT 10;",
        "sqlserver": f"-- SQL Server\nSELECT TOP 10 *\nFROM {get_tables(dataset)[0]};",
    }
    default = st.session_state.get(SK_EDITOR_SQL) or samples[dialect]
    key = f"ace_{st.session_state.get(SK_EDITOR_KEY, 0)}"

    if ACE_AVAILABLE:
        val = st_ace(value=default, language="sql", theme="tomorrow", height=220,
                     show_gutter=True, show_print_margin=False, wrap=True,
                     auto_update=True, key=key, placeholder=samples[dialect])
        return val if val is not None else default
    else:
        return st.text_area("SQL Editor (install streamlit-ace for syntax highlighting)",
                            value=default, height=220, key=f"ta_{key}") or default


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(page_title="SQL Practice Lab", page_icon="🎯",
                       layout="wide", initial_sidebar_state="expanded")

    # Session state defaults
    for k, v in [(SK_CONN, None), (SK_DIALECT, "mysql"), (SK_DATASET, "employees"),
                 (SK_EDITOR_SQL, ""), (SK_EDITOR_KEY, 0),
                 (SK_HISTORY, []), (SK_LAST_RESULT, None), (SK_ACTIVE_Q, None)]:
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state[SK_CONN] is None:
        with st.spinner("Initialising in-memory database…"):
            st.session_state[SK_CONN] = init_db()

    conn: sqlite3.Connection = st.session_state[SK_CONN]

    # ── Sidebar ─────────────────────────────────────────────
    with st.sidebar:
        st.title("🎯 SQL Practice Lab")
        st.caption("In-memory SQLite · No install needed")
        st.divider()

        dialect_choice = st.radio("SQL Dialect", list(DIALECTS.keys()),
                                  index=0 if st.session_state[SK_DIALECT]=="mysql" else 1,
                                  horizontal=True)
        st.session_state[SK_DIALECT] = DIALECTS[dialect_choice]

        dataset_choice = st.selectbox(
            "Dataset", DATASETS,
            index=DATASETS.index(st.session_state[SK_DATASET]),
            format_func=lambda x: {"employees":"👥 Employees","orders":"🛒 Orders",
                                   "library":"📚 Library","hospital":"🏥 Hospital"}[x])
        st.session_state[SK_DATASET] = dataset_choice

        with st.expander("📊 ER Diagram", expanded=False):
            st.code(ER_DIAGRAMS[dataset_choice], language=None)

        st.divider()
        render_schema_explorer(conn, dataset_choice)
        render_syntax_reference(st.session_state[SK_DIALECT])
        render_query_history()
        st.divider()
        st.caption("Built with Streamlit · SQLite · sqlglot")

    dialect = st.session_state[SK_DIALECT]
    dataset = st.session_state[SK_DATASET]

    tab1, tab2 = st.tabs(["🔬 Query Sandbox", "📝 Question Bank"])

    # ════════════════════════════════════════════════════════
    # TAB 1 — Query Sandbox
    # ════════════════════════════════════════════════════════
    with tab1:
        h1, h2 = st.columns([3, 1])
        with h1: st.subheader("Query Sandbox")
        with h2: st.markdown(f"{_dialect_badge(dialect)} · {_dataset_badge(dataset)}")

        current_sql = render_sql_editor(dialect, dataset)
        st.session_state[SK_EDITOR_SQL] = current_sql

        st.caption("💡 **Run Query** below — ACE editor also accepts Ctrl+Enter / Cmd+Enter")

        b1, b2, _ = st.columns([2, 1, 5])
        with b1: run_clicked = st.button("▶ Run Query", type="primary", width='stretch')
        with b2:
            if st.button("🗑️ Clear", width='stretch'):
                load_into_editor("")
                st.session_state[SK_LAST_RESULT] = None
                st.rerun()

        if run_clicked:
            sql_in = (current_sql or "").strip()
            if not sql_in:
                st.warning("⚠️ Editor is empty — write a query first.")
            else:
                result = run_query(conn, sql_in, dialect)
                st.session_state[SK_LAST_RESULT] = result
                add_to_history(sql_in, result.get("rowcount", 0))
                with st.expander("🔄 Translated SQL (SQLite)", expanded=False):
                    st.code(result.get("translated_sql") or sql_in, language="sql")
                render_results(result)

        elif st.session_state.get(SK_LAST_RESULT):
            st.divider()
            st.caption("*Last result:*")
            render_results(st.session_state[SK_LAST_RESULT])

    # ════════════════════════════════════════════════════════
    # TAB 2 — Question Bank
    # ════════════════════════════════════════════════════════
    with tab2:
        st.subheader("Question Bank")
        st.caption("Load a skeleton → write your solution in the Sandbox → Check My Answer.")

        f1, f2, f3 = st.columns(3)
        with f1: f_d = st.selectbox("Dialect", ["All","MySQL","SQL Server","Both"], key="qf_d")
        with f2: f_diff = st.selectbox("Difficulty", ["All","Intermediate","Expert"], key="qf_diff")
        with f3: f_ds = st.selectbox("Dataset", ["All"]+[d.capitalize() for d in DATASETS], key="qf_ds")

        dm = {"MySQL":"mysql","SQL Server":"sqlserver","Both":"both"}
        qs = QUESTIONS
        if f_d != "All":  qs = [q for q in qs if q["dialect"] in (dm[f_d], "both")]
        if f_diff != "All": qs = [q for q in qs if q["difficulty"] == f_diff.lower()]
        if f_ds != "All":  qs = [q for q in qs if q["dataset"] == f_ds.lower()]

        if not qs:
            st.info("No questions match those filters.")
        else:
            st.caption(f"Showing **{len(qs)}** question(s)")
            for q in qs:
                st.markdown("---")
                hc, bc = st.columns([4, 3])
                with hc: st.markdown(f"### {q['id']}. {q['title']}")
                with bc:
                    st.markdown(
                        f"{_diff_badge(q['difficulty'])} &nbsp;|&nbsp; "
                        f"{_dialect_badge(q['dialect'])} &nbsp;|&nbsp; "
                        f"{_dataset_badge(q['dataset'])}",
                        unsafe_allow_html=True)

                st.markdown(q["question"])

                with st.expander("💡 Show Hint"):
                    st.info(q["hint"])

                a1, a2, a3 = st.columns(3)

                with a1:
                    if st.button("📝 Load Skeleton", key=f"sk_{q['id']}"):
                        load_into_editor(SKELETONS.get(q["id"], f"-- Q{q['id']}\n"))
                        st.success(f"Skeleton loaded. Switch to **Query Sandbox** tab.")

                with a2:
                    if st.button("✅ Check My Answer", key=f"chk_{q['id']}"):
                        user_sql = (st.session_state.get(SK_EDITOR_SQL) or "").strip()
                        if not user_sql:
                            st.warning("Write your answer in the Sandbox editor first.")
                        else:
                            r = check_answer(conn, user_sql, q, dialect)
                            if r["passed"]:
                                st.success(f"✓ {r['message']}")
                            else:
                                st.error(f"✗ {r['message']}")
                                if r["expected_rowcount"] is not None:
                                    st.caption(f"Your rows: **{r['user_rowcount']}** · "
                                               f"Expected: **{r['expected_rowcount']}**")

                with a3:
                    rk = f"rev_{q['id']}"
                    if st.button("🔓 Reveal Solution", key=f"btn_{rk}"):
                        st.session_state[rk] = not st.session_state.get(rk, False)

                if st.session_state.get(f"rev_{q['id']}", False):
                    st.code(q["solution"], language="sql")
                    note = {"mysql": "✍️ MySQL dialect — uses CONCAT, LIMIT, IFNULL, DATEDIFF.",
                            "sqlserver": "✍️ SQL Server dialect — uses TOP, ISNULL, LEN, STRING_AGG.",
                            "both": "✍️ Standard SQL — works in both dialects (CTEs, window functions)."
                            }.get(q["dialect"], "")
                    if note: st.caption(note)


if __name__ == "__main__":
    main()
