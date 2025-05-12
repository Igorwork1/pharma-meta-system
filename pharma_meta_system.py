import streamlit as st
import pandas as pd
import psycopg2
import logging
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import io
import uuid
import re

# Настройка логирования
logging.basicConfig(
    filename='pharma_metadata.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_action(action, details=None, username=None):
    log_msg = f"{action} {'by ' + username if username else ''}"
    if details:
        log_msg += f" - Details: {details}"
    logging.info(log_msg)

def get_logs():
    with open('pharma_metadata.log', 'r') as f:
        return f.readlines()

# Настройка подключения к PostgreSQL
def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname="meta_base",
            user="postgres",
            password="1234",
            host="localhost",
            port="5432"
        )
        return conn
    except psycopg2.Error as e:
        st.error(f"Ошибка подключения к базе данных: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()

    # Создание таблицы companies
    c.execute('''CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        gln VARCHAR(20),
        name_short VARCHAR(50),
        name_full VARCHAR(100),
        gcp_compliant BOOLEAN,
        registration_country VARCHAR(50),
        address VARCHAR(200),
        type VARCHAR(50)
    )''')

    # Создание таблицы medicines
    c.execute('''CREATE TABLE IF NOT EXISTS medicines (
        id SERIAL PRIMARY KEY,
        owned_by INTEGER,
        name VARCHAR(50),
        gtin VARCHAR(20),
        sku VARCHAR(20),
        market VARCHAR(20),
        shared BOOLEAN DEFAULT FALSE,
        batch_number VARCHAR(50),
        expiration_date DATE,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owned_by) REFERENCES companies(id) ON DELETE SET NULL
    )''')

    # Создание таблицы locations
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
        id SERIAL PRIMARY KEY,
        owned_by INTEGER,
        gln VARCHAR(20),
        country VARCHAR(50),
        address VARCHAR(200),
        role VARCHAR(50),
        name_short VARCHAR(50),
        name_full VARCHAR(100),
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owned_by) REFERENCES companies(id) ON DELETE SET NULL
    )''')

    # Создание таблицы operations
    c.execute('''CREATE TABLE IF NOT EXISTS operations (
        id SERIAL PRIMARY KEY,
        medicine_id INTEGER,
        location_id INTEGER,
        operation_type VARCHAR(50),
        operation_date TIMESTAMP,
        quantity INTEGER,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE SET NULL,
        FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
    )''')

    # Создание таблицы users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        login VARCHAR(20) UNIQUE,
        password VARCHAR(50),
        role VARCHAR(20),
        first_name VARCHAR(50),
        last_name VARCHAR(50),
        email VARCHAR(100)
    )''')

    # Добавление столбца medicine_id, если он отсутствует
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'operations' AND column_name = 'medicine_id'")
    if not c.fetchone():
        c.execute("ALTER TABLE operations ADD COLUMN medicine_id INTEGER REFERENCES medicines(id) ON DELETE SET NULL")

    # Добавление столбца location_id, если он отсутствует
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'operations' AND column_name = 'location_id'")
    if not c.fetchone():
        c.execute("ALTER TABLE operations ADD COLUMN location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL")

    # Удаление ограничений UNIQUE для gtin и sku, если они существуют
    c.execute("SELECT constraint_name FROM information_schema.table_constraints WHERE table_name = 'medicines' AND constraint_type = 'UNIQUE' AND constraint_name LIKE '%gtin%'")
    gtin_constraint = c.fetchone()
    if gtin_constraint:
        c.execute(f"ALTER TABLE medicines DROP CONSTRAINT {gtin_constraint[0]}")

    c.execute("SELECT constraint_name FROM information_schema.table_constraints WHERE table_name = 'medicines' AND constraint_type = 'UNIQUE' AND constraint_name LIKE '%sku%'")
    sku_constraint = c.fetchone()
    if sku_constraint:
        c.execute(f"ALTER TABLE medicines DROP CONSTRAINT {sku_constraint[0]}")

    conn.commit()
    conn.close()

# Функции получения данных
def get_medications():
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    df = pd.read_sql_query("SELECT * FROM medicines", conn)
    conn.close()
    return df

def get_companies():
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    df = pd.read_sql_query("SELECT * FROM companies", conn)
    conn.close()
    return df

def get_locations():
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    df = pd.read_sql_query("SELECT * FROM locations", conn)
    conn.close()
    return df

def get_operations():
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    df = pd.read_sql_query("SELECT * FROM operations", conn)
    conn.close()
    return df

# Функции добавления
def add_medication(name, gtin, sku, market, batch_number, expiration_date, owned_by, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO medicines 
                     (name, gtin, sku, market, shared, batch_number, expiration_date, owned_by, created_date) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                  (name, gtin, sku, market, False, batch_number, expiration_date, owned_by,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        log_action("Added medication", f"ID: {c.lastrowid}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка добавления медикамента: {e}")
    finally:
        conn.close()

def add_company(gln, name_short, name_full, gcp_compliant, registration_country, address, type, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO companies 
                     (gln, name_short, name_full, gcp_compliant, registration_country, address, type) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                  (gln, name_short, name_full, gcp_compliant, registration_country, address, type))
        conn.commit()
        log_action("Added company", f"ID: {c.lastrowid}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка добавления компании: {e}")
    finally:
        conn.close()

def add_location(gln, country, address, role, name_short, name_full, owned_by, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO locations 
                     (gln, country, address, role, name_short, name_full, owned_by, created_date) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                  (gln, country, address, role, name_short, name_full, owned_by,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        log_action("Added location", f"ID: {c.lastrowid}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка добавления локации: {e}")
    finally:
        conn.close()

def add_operation(medicine_id, location_id, operation_type, operation_date, quantity, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO operations 
                     (medicine_id, location_id, operation_type, operation_date, quantity, created_date) 
                     VALUES (%s, %s, %s, %s, %s, %s)''',
                  (medicine_id, location_id, operation_type, operation_date, quantity,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        log_action("Added operation", f"ID: {c.lastrowid}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка добавления операции: {e}")
    finally:
        conn.close()

# Функции редактирования
def edit_medication(med_id, name, gtin, sku, market, batch_number, expiration_date, owned_by, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''UPDATE medicines 
                     SET name=%s, gtin=%s, sku=%s, market=%s, batch_number=%s, expiration_date=%s, owned_by=%s 
                     WHERE id=%s''',
                  (name, gtin, sku, market, batch_number, expiration_date, owned_by, med_id))
        conn.commit()
        log_action("Edited medication", f"ID: {med_id}, Changed fields: {', '.join([f'{k}={v}' for k, v in {'name': name, 'gtin': gtin, 'sku': sku, 'market': market, 'batch_number': batch_number, 'expiration_date': str(expiration_date), 'owned_by': owned_by}.items() if v])}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка редактирования медикамента: {e}")
    finally:
        conn.close()

def edit_company(company_id, gln, name_short, name_full, gcp_compliant, registration_country, address, type, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''UPDATE companies 
                     SET gln=%s, name_short=%s, name_full=%s, gcp_compliant=%s, registration_country=%s, address=%s, type=%s 
                     WHERE id=%s''',
                  (gln, name_short, name_full, gcp_compliant, registration_country, address, type, company_id))
        conn.commit()
        log_action("Edited company", f"ID: {company_id}, Changed fields: {', '.join([f'{k}={v}' for k, v in {'gln': gln, 'name_short': name_short, 'name_full': name_full, 'gcp_compliant': str(gcp_compliant), 'registration_country': registration_country, 'address': address, 'type': type}.items() if v])}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка редактирования компании: {e}")
    finally:
        conn.close()

def edit_location(location_id, gln, country, address, role, name_short, name_full, owned_by, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''UPDATE locations 
                     SET gln=%s, country=%s, address=%s, role=%s, name_short=%s, name_full=%s, owned_by=%s 
                     WHERE id=%s''',
                  (gln, country, address, role, name_short, name_full, owned_by, location_id))
        conn.commit()
        log_action("Edited location", f"ID: {location_id}, Changed fields: {', '.join([f'{k}={v}' for k, v in {'gln': gln, 'country': country, 'address': address, 'role': role, 'name_short': name_short, 'name_full': name_full, 'owned_by': owned_by}.items() if v])}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка редактирования локации: {e}")
    finally:
        conn.close()

def edit_operation(operation_id, medicine_id, location_id, operation_type, operation_date, quantity, username):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute('''UPDATE operations 
                     SET medicine_id=%s, location_id=%s, operation_type=%s, operation_date=%s, quantity=%s 
                     WHERE id=%s''',
                  (medicine_id, location_id, operation_type, operation_date, quantity, operation_id))
        conn.commit()
        log_action("Edited operation", f"ID: {operation_id}, Changed fields: {', '.join([f'{k}={v}' for k, v in {'medicine_id': medicine_id, 'location_id': location_id, 'operation_type': operation_type, 'operation_date': str(operation_date), 'quantity': quantity}.items() if v])}", username)
    except psycopg2.Error as e:
        st.error(f"Ошибка редактирования операции: {e}")
    finally:
        conn.close()

# Функции удаления с проверкой зависимостей
def delete_medication(med_id):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM operations WHERE medicine_id = %s", (med_id,))
        if c.fetchone()[0] > 0:
            st.error("Нельзя удалить медикамент, так как он связан с операциями")
            return
        c.execute("DELETE FROM medicines WHERE id=%s", (med_id,))
        conn.commit()
        log_action("Deleted medication", f"ID: {med_id}")
    except psycopg2.Error as e:
        st.error(f"Ошибка удаления медикамента: {e}")
    finally:
        conn.close()

def delete_company(company_id):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM medicines WHERE owned_by = %s", (company_id,))
        med_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM locations WHERE owned_by = %s", (company_id,))
        loc_count = c.fetchone()[0]
        if med_count > 0 or loc_count > 0:
            st.error("Нельзя удалить компанию, так как у неё есть связанные Препараты или локации")
            return
        c.execute("DELETE FROM companies WHERE id=%s", (company_id,))
        conn.commit()
        log_action("Deleted company", f"ID: {company_id}")
    except psycopg2.Error as e:
        st.error(f"Ошибка удаления компании: {e}")
    finally:
        conn.close()

def delete_location(location_id):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM operations WHERE location_id = %s", (location_id,))
        if c.fetchone()[0] > 0:
            st.error("Нельзя удалить локацию, так как она связана с операциями")
            return
        c.execute("DELETE FROM locations WHERE id=%s", (location_id,))
        conn.commit()
        log_action("Deleted location", f"ID: {location_id}")
    except psycopg2.Error as e:
        st.error(f"Ошибка удаления локации: {e}")
    finally:
        conn.close()

def delete_operation(operation_id):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        c.execute("DELETE FROM operations WHERE id=%s", (operation_id,))
        conn.commit()
        log_action("Deleted operation", f"ID: {operation_id}")
    except psycopg2.Error as e:
        st.error(f"Ошибка удаления операции: {e}")
    finally:
        conn.close()

# Импорт/экспорт данных
def import_data(file):
    conn = get_db_connection()
    if conn is None:
        return
    c = conn.cursor()
    try:
        if file.type in ['text/csv', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
            df = pd.read_csv(file) if file.type == 'text/csv' else pd.read_excel(file)
            table = df.columns[0].split('_')[0]
            if table == 'medicines':
                for _, row in df.iterrows():
                    c.execute('''SELECT id FROM medicines 
                                 WHERE name = %s AND gtin = %s AND sku = %s AND market = %s 
                                 AND batch_number = %s AND expiration_date = %s AND owned_by = %s''',
                              (row['name'], row['gtin'], row['sku'], row['market'], row['batch_number'],
                               row['expiration_date'], row['owned_by']))
                    if c.fetchone():
                        continue
                    c.execute('''INSERT INTO medicines 
                                 (name, gtin, sku, market, shared, batch_number, expiration_date, owned_by, created_date) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                              (row['name'], row['gtin'], row['sku'], row['market'], row['shared'], row['batch_number'],
                               row['expiration_date'], row['owned_by'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            elif table == 'companies':
                for _, row in df.iterrows():
                    c.execute('''SELECT id FROM companies 
                                 WHERE gln = %s AND name_short = %s AND name_full = %s 
                                 AND gcp_compliant = %s AND registration_country = %s 
                                 AND address = %s AND type = %s''',
                              (row['gln'], row['name_short'], row['name_full'], row['gcp_compliant'],
                               row['registration_country'], row['address'], row['type']))
                    if c.fetchone():
                        continue
                    c.execute('''INSERT INTO companies 
                                 (gln, name_short, name_full, gcp_compliant, registration_country, address, type) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                              (row['gln'], row['name_short'], row['name_full'], row['gcp_compliant'],
                               row['registration_country'], row['address'], row['type']))
            elif table == 'locations':
                for _, row in df.iterrows():
                    c.execute('''INSERT INTO locations 
                                 (gln, country, address, role, name_short, name_full, owned_by, created_date) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                              (row['gln'], row['country'], row['address'], row['role'], row['name_short'],
                               row['name_full'], row['owned_by'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            elif table == 'operations':
                for _, row in df.iterrows():
                    c.execute('''INSERT INTO operations 
                                 (medicine_id, location_id, operation_type, operation_date, quantity, created_date) 
                                 VALUES (%s, %s, %s, %s, %s, %s)''',
                              (row['medicine_id'], row['location_id'], row['operation_type'], row['operation_date'],
                               row['quantity'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            log_action(f"Imported data into {table}", f"Rows: {len(df)}")
            st.success(f"Импортировано {len(df)} записей в таблицу {table}")
        else:
            st.error("Поддерживаются только CSV и Excel файлы")
    except Exception as e:
        st.error(f"Ошибка импорта: {e}")
    finally:
        conn.close()

def export_data(table):
    conn = get_db_connection()
    if conn is None:
        return
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    conn.close()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=table, index=False)
    log_action(f"Exported data from {table}", f"Rows: {len(df)}")
    st.download_button(label=f"Экспорт {table}", data=output.getvalue(),
                      file_name=f"{table}_export.xlsx",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Валидация данных
def validate_medication_data(name, gtin, sku, market, batch_number, expiration_date, owned_by):
    errors = []
    if not name:
        errors.append("Название не может быть пустым")
    if not gtin or len(gtin) > 20:
        errors.append("GTIN должен быть непустым и не длиннее 20 символов")
    if not sku or len(sku) > 20:
        errors.append("SKU должен быть непустым и не длиннее 20 символов")
    if not market:
        errors.append("Рынок не может быть пустым")
    if not batch_number:
        errors.append("Номер партии не может быть пустым")
    if not expiration_date:
        errors.append("Срок годности обязателен")
    if not owned_by:
        errors.append("Компания-владелец обязательна")
    return errors

def validate_company_data(gln, name_short, name_full, gcp_compliant, registration_country, address, type):
    errors = []
    if not name_short:
        errors.append("Краткое название не может быть пустым")
    if len(name_short) > 50:
        errors.append("Краткое название не должно превышать 50 символов")
    if not name_full:
        errors.append("Полное название не может быть пустым")
    if len(name_full) > 100:
        errors.append("Полное название не должно превышать 100 символов")
    if gln and len(gln) > 20:
        errors.append("GLN не должен превышать 20 символов")
    if registration_country and len(registration_country) > 50:
        errors.append("Страна регистрации не должна превышать 50 символов")
    if address and len(address) > 200:
        errors.append("Адрес не должен превышать 200 символов")
    if type and len(type) > 50:
        errors.append("Тип не должен превышать 50 символов")
    return errors

def validate_location_data(gln, country, address, role, name_short, name_full, owned_by):
    errors = []
    if not address:
        errors.append("Адрес не может быть пустым")
    if len(address) > 200:
        errors.append("Адрес не должен превышать 200 символов")
    if gln and len(gln) > 20:
        errors.append("GLN не должен превышать 20 символов")
    if country and len(country) > 50:
        errors.append("Страна не должна превышать 50 символов")
    if role and len(role) > 50:
        errors.append("Роль не должна превышать 50 символов")
    if name_short and len(name_short) > 50:
        errors.append("Краткое название не должно превышать 50 символов")
    if name_full and len(name_full) > 100:
        errors.append("Полное название не должно превышать 100 символов")
    if not owned_by:
        errors.append("Компания-владелец обязательна")
    return errors

def validate_operation_data(medicine_id, location_id, operation_type, operation_date, quantity):
    errors = []
    if not medicine_id:
        errors.append("ID медикамента обязателен")
    if not location_id:
        errors.append("ID локации обязателен")
    if not operation_type:
        errors.append("Тип операции не может быть пустым")
    if not operation_date:
        errors.append("Дата операции обязательна")
    if not quantity or quantity <= 0:
        errors.append("Количество должно быть больше 0")
    return errors

# Функция авторизации
def login(username, password):
    conn = get_db_connection()
    if conn is None:
        return False
    c = conn.cursor()
    try:
        c.execute("SELECT password, role FROM users WHERE login = %s", (username,))
        result = c.fetchone()
        if result and result[0] == password:
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.session_state['role'] = result[1]
            log_action(f"Успешный вход пользователя: {username}")
            return True
        log_action(f"Неуспешная попытка входа: {username}")
        return False
    except psycopg2.Error as e:
        st.error(f"Ошибка базы данных: {e}")
        return False
    finally:
        conn.close()

# Интерфейс авторизации
def auth_interface():
    st.markdown("""
    <style>
        .login-container h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 28px;
        }
        .stButton > button {
            background-color: #4CAF50;
            color: white;
            padding: 12px 24px;
            font-size: 18px;
            border-radius: 5px;
            border: none;
            cursor: pointer;
            width: 100%;
        }
        .stButton > button:hover {
            background-color: #45a049;
        }
        .error-message {
            color: #d32f2f;
            font-size: 16px;
            margin-top: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<h2>Авторизация</h2>', unsafe_allow_html=True)
    
    username = st.text_input("Логин", key="login_username", placeholder="Введите логин")
    password = st.text_input("Пароль", type="password", key="login_password", placeholder="Введите пароль")
    
    if st.button("Войти"):
        if login(username, password):
            st.success("Успешный вход!")
            st.rerun()
        else:
            st.markdown('<p class="error-message">Неверный логин или пароль</p>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# Интерфейс и страницы
def show_view_data():
    st.subheader("Просмотр данных")
    entity = st.selectbox("Выберите тип данных", ["Препараты", "Компании", "Локации", "Операции"])
    if entity == "Препараты":
        df = get_medications()
    elif entity == "Компании":
        df = get_companies()
    elif entity == "Локации":
        df = get_locations()
    else:
        df = get_operations()
    if not df.empty:
        st.write("### Данные")
        st.dataframe(df)
        st.write("### Числовая статистика")
        numeric_df = df.select_dtypes(include=['int64', 'float64'])
        if not numeric_df.empty:
            st.dataframe(numeric_df.describe())
        else:
            st.info("Нет числовых данных для статистики.")
        st.write("### Категориальная статистика")
        categorical_df = df.select_dtypes(include=['object', 'bool'])
        if not categorical_df.empty:
            st.dataframe(categorical_df.describe())
        else:
            st.info("Нет категориальных данных для статистики.")
        if st.button("Экспорт", key=f"export_{entity.lower()}_data"):
            export_data(entity.lower())
    else:
        st.warning(f"Нет данных для отображения. Добавьте {entity.lower()} на странице 'Добавить'.")

def show_edit_delete_data():
    if st.session_state['role'] not in ['admin', 'analyst']:
        st.error("Доступ запрещен")
        return
    st.subheader("Редактировать или удалить запись")
    action = st.radio("Выберите действие", ["Редактировать", "Удалить"], horizontal=True)
    entity = st.selectbox("Выберите тип записи", ["Препараты", "Компании", "Локации", "Операции"])

    if action == "Удалить":
        if entity == "Препараты":
            med_id = st.number_input("ID медикамента для удаления", min_value=1)
            if st.button("Удалить"):
                delete_medication(med_id)
                st.success("Медикамент удален!")
        elif entity == "Компании":
            company_id = st.number_input("ID компании для удаления", min_value=1)
            if st.button("Удалить"):
                delete_company(company_id)
                st.success("Компания удалена!")
        elif entity == "Локации":
            location_id = st.number_input("ID локации для удаления", min_value=1)
            if st.button("Удалить"):
                delete_location(location_id)
                st.success("Локация удалена!")
        else:
            operation_id = st.number_input("ID операции для удаления", min_value=1)
            if st.button("Удалить"):
                delete_operation(operation_id)
                st.success("Операция удалена!")
    else:
        record_id = st.number_input("ID записи для редактирования", min_value=1)
        conn = get_db_connection()
        if conn is None:
            return
        c = conn.cursor()
        if entity == "Препараты":
            c.execute("SELECT * FROM medicines WHERE id = %s", (record_id,))
            record = c.fetchone()
            if record:
                df = pd.DataFrame([record], columns=['id', 'owned_by', 'name', 'gtin', 'sku', 'market', 'shared', 'batch_number', 'expiration_date', 'created_date'])
                companies = get_companies()
                company_options = {f"{row['name_full']} (ID: {row['id']})": row['id'] for _, row in companies.iterrows()} if not companies.empty else {"Нет компаний": None}
                with st.form(key=f"edit_med_{record_id}_{uuid.uuid4()}"):
                    name = st.text_input("Название", value=df['name'].iloc[0], help="Название медикамента (до 50 символов)")
                    gtin = st.text_input("GTIN", value=df['gtin'].iloc[0], help="Глобальный номер товара (до 20 символов)")
                    sku = st.text_input("SKU", value=df['sku'].iloc[0], help="Внутренний артикул (до 20 символов)")
                    market = st.text_input("Рынок", value=df['market'].iloc[0], help="Целевой рынок (до 20 символов)")
                    batch_number = st.text_input("Номер партии", value=df['batch_number'].iloc[0], help="Уникальный номер партии (до 50 символов)")
                    expiration_date = st.date_input("Срок годности", value=pd.to_datetime(df['expiration_date'].iloc[0]), help="Дата окончания срока годности")
                    owned_by_choice = st.selectbox("Компания-владелец", list(company_options.keys()), index=list(company_options.keys()).index(next((k for k, v in company_options.items() if v == df['owned_by'].iloc[0]), 0)), help="Выберите компанию-владельца")
                    if st.form_submit_button("Сохранить"):
                        errors = validate_medication_data(name, gtin, sku, market, batch_number, expiration_date, company_options[owned_by_choice])
                        if errors:
                            for error in errors:
                                st.error(error)
                        else:
                            c.execute('''SELECT id FROM medicines 
                                         WHERE name = %s AND gtin = %s AND sku = %s AND market = %s 
                                         AND batch_number = %s AND expiration_date = %s AND owned_by = %s 
                                         AND id != %s''',
                                      (name, gtin, sku, market, batch_number, expiration_date, company_options[owned_by_choice], record_id))
                            if c.fetchone():
                                st.error("Такая запись уже существует")
                            else:
                                edit_medication(record_id, name, gtin, sku, market, batch_number, expiration_date, company_options[owned_by_choice], st.session_state['username'])
                                st.success("Медикамент обновлен!")
        elif entity == "Компании":
            c.execute("SELECT * FROM companies WHERE id = %s", (record_id,))
            record = c.fetchone()
            if record:
                df = pd.DataFrame([record], columns=['id', 'gln', 'name_short', 'name_full', 'gcp_compliant', 'registration_country', 'address', 'type'])
                with st.form(key=f"edit_comp_{record_id}_{uuid.uuid4()}"):
                    gln = st.text_input("GLN", value=df['gln'].iloc[0], help="Глобальный номер местоположения (до 20 символов)")
                    name_short = st.text_input("Краткое название", value=df['name_short'].iloc[0], help="Краткое название компании (до 50 символов)")
                    name_full = st.text_input("Полное название", value=df['name_full'].iloc[0], help="Полное название компании (до 100 символов)")
                    gcp_compliant = st.checkbox("GCP-совместимость", value=df['gcp_compliant'].iloc[0], help="Соответствие стандартам GCP")
                    registration_country = st.text_input("Страна регистрации", value=df['registration_country'].iloc[0], help="Страна регистрации (до 50 символов)")
                    address = st.text_input("Адрес", value=df['address'].iloc[0], help="Адрес компании (до 200 символов)")
                    type = st.text_input("Тип", value=df['type'].iloc[0], help="Тип компании (например, Производитель, до 50 символов)")
                    if st.formNft_button("Сохранить"):
                        errors = validate_company_data(gln, name_short, name_full, gcp_compliant, registration_country, address, type)
                        if errors:
                            for error in errors:
                                st.error(error)
                        else:
                            c.execute('''SELECT id FROM companies 
                                         WHERE gln = %s AND name_short = %s AND name_full = %s 
                                         AND gcp_compliant = %s AND registration_country = %s 
                                         AND address = %s AND type = %s AND id != %s''',
                                      (gln, name_short, name_full, gcp_compliant, registration_country, address, type, record_id))
                            if c.fetchone():
                                st.error("Такая запись уже существует")
                            else:
                                edit_company(record_id, gln, name_short, name_full, gcp_compliant, registration_country, address, type, st.session_state['username'])
                                st.success("Компания обновлена!")
        elif entity == "Локации":
            c.execute("SELECT * FROM locations WHERE id = %s", (record_id,))
            record = c.fetchone()
            if record:
                df = pd.DataFrame([record], columns=['id', 'owned_by', 'gln', 'country', 'address', 'role', 'name_short', 'name_full', 'created_date'])
                companies = get_companies()
                company_options = {f"{row['name_full']} (ID: {row['id']})": row['id'] for _, row in companies.iterrows()} if not companies.empty else {"Нет компаний": None}
                with st.form(key=f"edit_loc_{record_id}_{uuid.uuid4()}"):
                    gln = st.text_input("GLN", value=df['gln'].iloc[0], help="Глобальный номер местоположения (до 20 символов)")
                    country = st.text_input("Страна", value=df['country'].iloc[0], help="Страна локации (до 50 символов)")
                    address = st.text_input("Адрес", value=df['address'].iloc[0], help="Адрес локации (до 200 символов)")
                    role = st.text_input("Роль", value=df['role'].iloc[0], help="Роль локации (например, Склад, до 50 символов)")
                    name_short = st.text_input("Краткое название", value=df['name_short'].iloc[0], help="Краткое название локации (до 50 символов)")
                    name_full = st.text_input("Полное название", value=df['name_full'].iloc[0], help="Полное название локации (до 100 символов)")
                    owned_by_choice = st.selectbox("Компания-владелец", list(company_options.keys()), index=list(company_options.keys()).index(next((k for k, v in company_options.items() if v == df['owned_by'].iloc[0]), 0)), help="Выберите компанию-владельца")
                    if st.form_submit_button("Сохранить"):
                        errors = validate_location_data(gln, country, address, role, name_short, name_full, company_options[owned_by_choice])
                        if errors:
                            for error in errors:
                                st.error(error)
                        else:
                            edit_location(record_id, gln, country, address, role, name_short, name_full, company_options[owned_by_choice], st.session_state['username'])
                            st.success("Локация обновлена!")
        elif entity == "Операции":
            c.execute("SELECT * FROM operations WHERE id = %s", (record_id,))
            record = c.fetchone()
            if record:
                df = pd.DataFrame([record], columns=['id', 'medicine_id', 'location_id', 'operation_type', 'operation_date', 'quantity', 'created_date'])
                medicines = get_medications()
                locations = get_locations()
                medicine_options = {f"{row['name']} (ID: {row['id']})": row['id'] for _, row in medicines.iterrows()} if not medicines.empty else {"Нет медикаментов": None}
                location_options = {f"{row['name_short'] or row['name_full'] or f'Локация ID {row['id']}'} (ID: {row['id']})": row['id'] for _, row in locations.iterrows()} if not locations.empty else {"Нет локаций": None}
                with st.form(key=f"edit_op_{record_id}_{uuid.uuid4()}"):
                    medicine_choice = st.selectbox("Медикамент", list(medicine_options.keys()), index=list(medicine_options.keys()).index(next((k for k, v in medicine_options.items() if v == df['medicine_id'].iloc[0]), 0)), help="Выберите медикамент")
                    location_choice = st.selectbox("Локация", list(location_options.keys()), index=list(location_options.keys()).index(next((k for k, v in location_options.items() if v == df['location_id'].iloc[0]), 0)), help="Выберите локацию")
                    operation_type = st.selectbox("Тип операции", ["Агрегация", "Дистрибьютор", "Поставка", "Списание", "Производство", "Перемещение"], index=["Агрегация", "Дистрибьютор", "Поставка", "Списание", "Производство", "Перемещение"].index(df['operation_type'].iloc[0]), help="Выберите тип операции")
                    operation_date = st.date_input("Дата операции", value=pd.to_datetime(df['operation_date'].iloc[0]), help="Дата выполнения операции")
                    quantity = st.number_input("Количество", min_value=1, value=df['quantity'].iloc[0], help="Количество единиц")
                    if st.form_submit_button("Сохранить"):
                        errors = validate_operation_data(medicine_options[medicine_choice], location_options[location_choice], operation_type, operation_date, quantity)
                        if errors:
                            for error in errors:
                                st.error(error)
                        else:
                            edit_operation(record_id, medicine_options[medicine_choice], location_options[location_choice], operation_type, operation_date, quantity, st.session_state['username'])
                            st.success("Операция обновлена!")
        conn.close()

def show_add_data():
    st.subheader("Добавить новую запись")
    entity = st.selectbox("Выберите тип записи", ["Препараты", "Компании", "Локации", "Операции"])
    if entity == "Препараты":
        companies = get_companies()
        company_options = {f"{row['name_full']} (ID: {row['id']})": row['id'] for _, row in companies.iterrows()} if not companies.empty else {"Нет компаний": None}
        with st.form(key="add_med"):
            name = st.text_input("Название", help="Название медикамента (до 50 символов)")
            gtin = st.text_input("GTIN", help="Глобальный номер товара (до 20 символов)")
            sku = st.text_input("SKU", help="Внутренний артикул (до 20 символов)")
            market = st.text_input("Рынок", help="Целевой рынок (до 20 символов)")
            batch_number = st.text_input("Номер партии", help="Уникальный номер партии (до 50 символов)")
            expiration_date = st.date_input("Срок годности", help="Дата окончания срока годности")
            owned_by_choice = st.selectbox("Компания-владелец", list(company_options.keys()), help="Выберите компанию-владельца")
            uploaded_file = st.file_uploader("Импорт из CSV/Excel", type=['csv', 'xlsx'], key="med_import")
            if uploaded_file:
                import_data(uploaded_file)
            if st.form_submit_button("Добавить"):
                owned_by = company_options.get(owned_by_choice)
                errors = validate_medication_data(name, gtin, sku, market, batch_number, expiration_date, owned_by)
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    conn = get_db_connection()
                    if conn:
                        c = conn.cursor()
                        c.execute('''SELECT id FROM medicines 
                                     WHERE name = %s AND gtin = %s AND sku = %s AND market = %s 
                                     AND batch_number = %s AND expiration_date = %s AND owned_by = %s''',
                                  (name, gtin, sku, market, batch_number, expiration_date, owned_by))
                        if c.fetchone():
                            st.error("Такая запись уже существует")
                            conn.close()
                        else:
                            conn.close()
                            add_medication(name, gtin, sku, market, batch_number, expiration_date, owned_by, st.session_state['username'])
                            st.success("Медикамент добавлен!")
    elif entity == "Компании":
        with st.form(key="add_comp"):
            gln = st.text_input("GLN", help="Глобальный номер местоположения (до 20 символов)")
            name_short = st.text_input("Краткое название", help="Краткое название компании (до 50 символов)")
            name_full = st.text_input("Полное название", help="Полное название компании (до 100 символов)")
            gcp_compliant = st.checkbox("GCP-совместимость", help="Соответствие стандартам GCP")
            registration_country = st.text_input("Страна регистрации", help="Страна регистрации (до 50 символов)")
            address = st.text_input("Адрес", help="Адрес компании (до 200 символов)")
            type = st.text_input("Тип", help="Тип компании (например, Производитель, до 50 символов)")
            uploaded_file = st.file_uploader("Импорт из CSV/Excel", type=['csv', 'xlsx'], key="comp_import")
            if uploaded_file:
                import_data(uploaded_file)
            if st.form_submit_button("Добавить"):
                errors = validate_company_data(gln, name_short, name_full, gcp_compliant, registration_country, address, type)
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    conn = get_db_connection()
                    if conn:
                        c = conn.cursor()
                        c.execute('''SELECT id FROM companies 
                                     WHERE gln = %s AND name_short = %s AND name_full = %s 
                                     AND gcp_compliant = %s AND registration_country = %s 
                                     AND address = %s AND type = %s''',
                                  (gln, name_short, name_full, gcp_compliant, registration_country, address, type))
                        if c.fetchone():
                            st.error("Такая запись уже существует")
                            conn.close()
                        else:
                            conn.close()
                            add_company(gln, name_short, name_full, gcp_compliant, registration_country, address, type, st.session_state['username'])
                            st.success("Компания добавлена!")
    elif entity == "Локации":
        companies = get_companies()
        company_options = {f"{row['name_full']} (ID: {row['id']})": row['id'] for _, row in companies.iterrows()} if not companies.empty else {"Нет компаний": None}
        with st.form(key="add_loc"):
            gln = st.text_input("GLN", help="Глобальный номер местоположения (до 20 символов)")
            country = st.text_input("Страна", help="Страна локации (до 50 символов)")
            address = st.text_input("Адрес", help="Адрес локации (до 200 символов)")
            role = st.text_input("Роль", help="Роль локации (например, Склад, до 50 символов)")
            name_short = st.text_input("Краткое название", help="Краткое название локации (до 50 символов)")
            name_full = st.text_input("Полное название", help="Полное название локации (до 100 символов)")
            owned_by_choice = st.selectbox("Компания-владелец", list(company_options.keys()), help="Выберите компанию-владельца")
            uploaded_file = st.file_uploader("Импорт из CSV/Excel", type=['csv', 'xlsx'], key="loc_import")
            if uploaded_file:
                import_data(uploaded_file)
            if st.form_submit_button("Добавить"):
                owned_by = company_options.get(owned_by_choice)
                errors = validate_location_data(gln, country, address, role, name_short, name_full, owned_by)
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    add_location(gln, country, address, role, name_short, name_full, owned_by, st.session_state['username'])
                    st.success("Локация добавлена!")
    else:
        medicines = get_medications()
        locations = get_locations()
        medicine_options = {f"{row['name']} (ID: {row['id']})": row['id'] for _, row in medicines.iterrows()} if not medicines.empty else {"Нет медикаментов": None}
        location_options = {f"{row['name_short'] or row['name_full'] or f'Локация ID {row['id']}'} (ID: {row['id']})": row['id'] for _, row in locations.iterrows()} if not locations.empty else {"Нет локаций": None}
        with st.form(key="add_op"):
            medicine_choice = st.selectbox("Медикамент", list(medicine_options.keys()), help="Выберите медикамент")
            location_choice = st.selectbox("Локация", list(location_options.keys()), help="Выберите локацию")
            operation_type = st.selectbox("Тип операции", ["Агрегация", "Дистрибьютор", "Поставка", "Списание", "Производство", "Перемещение"], help="Выберите тип операции")
            operation_date = st.date_input("Дата операции", help="Дата выполнения операции")
            quantity = st.number_input("Количество", min_value=1, value=1, help="Количество единиц")
            uploaded_file = st.file_uploader("Импорт из CSV/Excel", type=['csv', 'xlsx'], key="op_import")
            if uploaded_file:
                import_data(uploaded_file)
            if st.form_submit_button("Добавить"):
                medicine_id = medicine_options.get(medicine_choice)
                location_id = location_options.get(location_choice)
                errors = validate_operation_data(medicine_id, location_id, operation_type, operation_date, quantity)
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    add_operation(medicine_id, location_id, operation_type, operation_date, quantity, st.session_state['username'])
                    st.success("Операция добавлена!")

def show_filter_data():
    st.subheader("Фильтрация")
    entity = st.selectbox("Выберите тип данных", ["Препараты", "Компании", "Локации", "Операции"])
    if entity == "Препараты":
        df = get_medications()
        filter_options = {
            "name": "Название",
            "gtin": "GTIN",
            "sku": "SKU",
            "market": "Рынок",
            "batch_number": "Номер партии",
            "expiration_date": "Срок годности",
            "created_date": "Дата создания",
            "owned_by": "ID компании-владельца"
        }
    elif entity == "Компании":
        df = get_companies()
        filter_options = {
            "gln": "GLN",
            "name_short": "Краткое название",
            "name_full": "Полное название",
            "gcp_compliant": "GCP-совместимость",
            "registration_country": "Страна регистрации",
            "address": "Адрес",
            "type": "Тип"
        }
    elif entity == "Локации":
        df = get_locations()
        filter_options = {
            "gln": "GLN",
            "country": "Страна",
            "address": "Адрес",
            "role": "Роль",
            "name_short": "Краткое название",
            "name_full": "Полное название",
            "owned_by": "ID компании-владельца",
            "created_date": "Дата создания"
        }
    else:
        df = get_operations()
        filter_options = {
            "medicine_id": "ID медикамента",
            "location_id": "ID локации",
            "operation_type": "Тип операции",
            "operation_date": "Дата операции",
            "quantity": "Количество",
            "created_date": "Дата создания"
        }

    if df.empty:
        st.warning(f"Нет данных для фильтрации. Добавьте {entity.lower()} на странице 'Добавить'.")
        return

    selected_filters = st.multiselect(
        "Выберите параметры для фильтрации",
        options=list(filter_options.keys()),
        format_func=lambda x: filter_options[x]
    )

    if not selected_filters:
        st.info("Выберите хотя бы один параметр для фильтрации.")
        return

    filter_values = {}
    for param in selected_filters:
        if param in ["name", "gtin", "sku", "market", "batch_number", "address", "gln", "country", "role", "name_short", "name_full", "registration_country", "type", "operation_type"]:
            filter_values[param] = st.text_input(f"Введите {filter_options[param]} (или оставьте пустым)")
        elif param in ["expiration_date", "operation_date", "created_date"]:
            filter_values[param] = st.date_input(f"Выберите {filter_options[param]}")
        elif param in ["quantity", "medicine_id", "location_id", "owned_by"]:
            filter_values[param] = st.number_input(f"Введите {filter_options[param]}", step=1)
        elif param == "gcp_compliant":
            filter_values[param] = st.selectbox(f"Выберите {filter_options[param]}", ["Любое", "Да", "Нет"])

    if st.button("Применить фильтр"):
        filtered_df = df.copy()
        for param in selected_filters:
            if param in ["name", "gtin", "sku", "market", "batch_number", "address", "gln", "country", "role", "name_short", "name_full", "registration_country", "type", "operation_type"]:
                if filter_values[param]:
                    filtered_df = filtered_df[filtered_df[param].str.contains(filter_values[param], case=False, na=False)]
            elif param in ["expiration_date", "operation_date", "created_date"]:
                filtered_df = filtered_df[filtered_df[param].astype(str).str.startswith(str(filter_values[param]), na=False)]
            elif param in ["quantity", "medicine_id", "location_id", "owned_by"]:
                filtered_df = filtered_df[filtered_df[param] == filter_values[param]]
            elif param == "gcp_compliant":
                if filter_values[param] != "Любое":
                    filtered_df = filtered_df[filtered_df[param] == (filter_values[param] == "Да")]
        if filtered_df.empty:
            st.warning("Нет данных, соответствующих выбранным фильтрам.")
        else:
            st.subheader("Отфильтрованные данные")
            st.dataframe(filtered_df)

def show_visualize():
    st.subheader("Визуализация данных")
    entity = st.selectbox("Выберите тип данных", ["Препараты", "Компании", "Локации", "Операции"])
    if entity == "Препараты":
        df = get_medications()
        if df.empty:
            st.warning("Нет данных для визуализации. Добавьте Препараты на странице 'Добавить'.")
            return
        viz_type = st.selectbox("Тип визуализации", ["Распределение по рынкам", "Доля медикаментов по сроку годности"])
        if viz_type == "Распределение по рынкам":
            plt.figure(figsize=(10, 6))
            sns.countplot(data=df, x='market')
            plt.xticks(rotation=45)
            plt.title("Распределение медикаментов по рынкам")
            st.pyplot(plt)
        else:
            current_date = pd.to_datetime("2025-05-10")
            df['days_to_expiry'] = (pd.to_datetime(df['expiration_date']) - current_date).dt.days
            df['expiry_status'] = pd.cut(df['days_to_expiry'],
                                        bins=[-float('inf'), 0, 180, 365, float('inf')],
                                        labels=['Просрочено', 'Менее 6 мес.', '6-12 мес.', 'Более года'])
            plt.figure(figsize=(8, 8))
            df['expiry_status'].value_counts().plot.pie(autopct='%1.1f%%')
            plt.title("Доля медикаментов по сроку годности")
            plt.ylabel('')
            st.pyplot(plt)
    elif entity == "Компании":
        df = get_companies()
        if df.empty:
            st.warning("Нет данных для визуализации. Добавьте компании на странице 'Добавить'.")
            return
        viz_type = st.selectbox("Тип визуализации", ["Распределение по странам регистрации", "Доля по типам компаний"])
        if viz_type == "Распределение по странам регистрации":
            plt.figure(figsize=(10, 6))
            sns.countplot(data=df, x='registration_country')
            plt.xticks(rotation=45)
            plt.title("Распределение компаний по странам регистрации")
            st.pyplot(plt)
        else:
            plt.figure(figsize=(8, 8))
            df['type'].value_counts().plot.pie(autopct='%1.1f%%')
            plt.title("Доля компаний по типам")
            plt.ylabel('')
            st.pyplot(plt)
    elif entity == "Локации":
        df = get_locations()
        if df.empty:
            st.warning("Нет данных для визуализации. Добавьте локации на странице 'Добавить'.")
            return
        viz_type = st.selectbox("Тип визуализации", ["Распределение по странам", "Расположение на карте"])
        if viz_type == "Распределение по странам":
            plt.figure(figsize=(10, 6))
            sns.countplot(data=df, x='country')
            plt.xticks(rotation=45)
            plt.title("Распределение локаций по странам")
            st.pyplot(plt)
        else:
            plt.figure(figsize=(10, 6))
            sns.scatterplot(data=df, x='name_short', y='country', hue='role', size='role')
            plt.xticks(rotation=45)
            plt.title("Локации по координатам")
            st.pyplot(plt)
    else:
        df = get_operations()
        if df.empty:
            st.warning("Нет данных для визуализации. Добавьте операции на странице 'Добавить'.")
            return
        viz_type = st.selectbox("Тип визуализации", ["Количество операций по датам", "Доля по типам операций"])
        if viz_type == "Количество операций по датам":
            df['operation_date'] = pd.to_datetime(df['operation_date'])
            df_grouped = df.groupby(df['operation_date'].dt.date)['quantity'].sum().reset_index()
            plt.figure(figsize=(10, 6))
            sns.lineplot(data=df_grouped, x='operation_date', y='quantity')
            plt.xticks(rotation=45)
            plt.title("Количество операций по датам")
            st.pyplot(plt)
        else:
            plt.figure(figsize=(8, 8))
            df['operation_type'].value_counts().plot.pie(autopct='%1.1f%%')
            plt.title("Доля операций по типам")
            plt.ylabel('')
            st.pyplot(plt)

def show_logs():
    st.subheader("Просмотр логов (Админ)")
    if st.session_state['role'] != 'admin':
        st.error("Доступ запрещен")
        return
    logs = get_logs()
    st.text_area("Логи", value="".join(logs), height=400)
    st.download_button(
        label="Скачать лог-файл",
        data="".join(logs),
        file_name="pharma_metadata.log",
        mime="text/plain"
    )

def show_home():
    st.subheader("Главная страница")
    st.write("""
    ### Добро пожаловать в Pharma Metadata System
    - **Версия**: 0.01
    - **Разработчик**: Kvinta
    - **Описание**: Система предназначена для управления данными о фармацевтических компаниях, медикаментах, локациях и операциях.
    - **Функции**:
      - Просмотр и добавление записей.
      - Редактирование и удаление данных (для администраторов и аналитиков).
      - Фильтрация и визуализация данных.
      - Импорт и экспорт данных в форматах CSV/Excel.
      - Логирование действий пользователей (для администраторов).
    - **Подсказки**:
      - GLN: 13-значный уникальный код (например, 1234567890123).
      - Роли локаций: Склад, Производство, Дистрибьютор.
      - Типы компаний: Производитель, Дистрибьютор, CMO, 3PL.
    """)

def main():
    st.title("Pharma Metadata System")
    init_db()

    st.markdown("""
    <style>
        body {
            font-size: 24px;
        }
        h1 {
            font-size: 25px;
        }
        h2 {
            font-size: 25px;
        }
        .stTextInput > div > div > input {
            font-size: 20px;
        }
        .stSelectbox > div > div > select {
            font-size: 20px;
        }
        .stDataFrame {
            font-size: 25px;
        }
        .stButton > button {
            font-size: 20px;
        }
        .footer {
            position: fixed;
            bottom: 15px;
            right: 15px;
            color: gray;
            font-size: 14px;
        }
    </style>
    """, unsafe_allow_html=True)

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.session_state['username'] = None

    if not st.session_state['logged_in']:
        auth_interface()
    else:
        if st.session_state['role'] == 'admin':
            menu = ["Главная страница", "Просмотр", "Добавить", "Редактировать", "Фильтр", "Визуализация", "Логи"]
        elif st.session_state['role'] == 'analyst':
            menu = ["Главная страница", "Просмотр", "Добавить", "Редактировать", "Фильтр", "Визуализация"]
        else:
            menu = ["Главная страница", "Просмотр", "Добавить"]

        st.sidebar.title(f"Добро пожаловать, {st.session_state['username']}")
        choice = st.sidebar.selectbox("Меню", menu, index=0)

        if choice == "Главная страница":
            show_home()
        elif choice == "Просмотр":
            show_view_data()
        elif choice == "Добавить":
            show_add_data()
        elif choice == "Редактировать":
            show_edit_delete_data()
        elif choice == "Фильтр":
            show_filter_data()
        elif choice == "Визуализация":
            show_visualize()
        elif choice == "Логи":
            show_logs()

        if st.sidebar.button("Выйти"):
            st.session_state['logged_in'] = False
            st.session_state['role'] = None
            log_action("User logged out", st.session_state['username'])
            st.session_state['username'] = None
            st.rerun()

    st.markdown(
        """
        <div class="footer">Принадлежит компании Kvinta, версия подсистемы 0.01</div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()