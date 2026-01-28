from flask import Flask, request, jsonify, send_file
import psycopg2
import os
from reportlab.pdfgen import canvas
import io
from datetime import datetime
from prometheus_client import start_http_server, Counter, Histogram, generate_latest

app = Flask(__name__)

# Prometheus Metrics
BOOKING_COUNT = Counter('booking_count', 'Total Bookings Created', ['doctor'])

# Database Config
DB_HOST = os.environ.get('DB_HOST', 'db')
DB_NAME = os.environ.get('DB_NAME', 'royal_clinic')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', 'password')

def get_db_connection():
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                patient_name VARCHAR(100) NOT NULL,
                place VARCHAR(100),
                age INTEGER,
                phone VARCHAR(20),
                dob DATE,
                doctor_name VARCHAR(100) NOT NULL,
                appointment_date DATE NOT NULL,
                token_number INTEGER NOT NULL
            );
        ''')
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

# Doctor Data
DOCTORS = [
    {
        "name": "Dr. Riyas",
        "specialty": "Ortho",
        "time": "10:00 AM - 01:00 PM",
        "days": [0, 1, 2, 3, 4] # Mon-Fri
    },
    {
        "name": "Dr. Joseph",
        "specialty": "Skin",
        "time": "03:00 PM - 07:00 PM",
        "days": [2, 3, 4, 5] # Wed-Sat
    },
    {
        "name": "Dr. Prakash",
        "specialty": "General",
        "time": "01:00 PM - 08:00 PM",
        "days": [0, 1, 2, 3, 4, 5] # Mon-Sat
    }
]

MAX_TOKENS = 50

@app.route('/metrics')
def metrics():
    return generate_latest()

@app.route('/doctors', methods=['GET'])
def get_doctors():
    return jsonify(DOCTORS)

@app.route('/book', methods=['POST'])
def book_appointment():
    data = request.json
    doctor_name = data.get('doctor_name')
    date_str = data.get('date')
    
    # Validate Date
    try:
        appt_date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    # Find Doctor
    doctor = next((d for d in DOCTORS if d["name"] == doctor_name), None)
    if not doctor:
        return jsonify({"error": "Doctor not found"}), 404

    # Check Day Availability
    if appt_date.weekday() not in doctor['days']:
        return jsonify({"error": f"{doctor_name} is not available on this day."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check Token Limit
    cur.execute("SELECT COUNT(*) FROM bookings WHERE doctor_name = %s AND appointment_date = %s", (doctor_name, date_str))
    count = cur.fetchone()[0]

    if count >= MAX_TOKENS:
        cur.close()
        conn.close()
        return jsonify({"error": "Daily token limit (50) reached for this doctor."}), 400

    token_number = count + 1
    
    # Insert Booking
    try:
        cur.execute('''
            INSERT INTO bookings (patient_name, place, age, phone, dob, doctor_name, appointment_date, token_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (data['patient_name'], data['place'], data['age'], data['phone'], data['dob'], doctor_name, date_str, token_number))
        
        booking_id = cur.fetchone()[0]
        conn.commit()
        BOOKING_COUNT.labels(doctor=doctor_name).inc()
        
        return jsonify({
            "message": "Booking Successful",
            "token_number": token_number,
            "booking_id": booking_id
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/download-pdf/<int:booking_id>', methods=['GET'])
def download_pdf(booking_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT patient_name, place, age, phone, dob, doctor_name, appointment_date, token_number 
        FROM bookings WHERE id = %s
    ''', (booking_id,))
    booking = cur.fetchone()
    cur.close()
    conn.close()

    if not booking:
        return "Booking not found", 404

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    
    # Header
    p.setFont("Helvetica-Bold", 18)
    p.drawString(200, 800, "ROYAL CLINIC - KUTTIPPURAM")
    p.setFont("Helvetica", 12)
    p.drawString(230, 780, "Appointment Receipt")
    
    p.line(50, 760, 550, 760)
    
    # Content
    y = 730
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, y, f"Token Number: {booking[7]}")
    y -= 30
    
    p.setFont("Helvetica", 12)
    p.drawString(50, y, f"Doctor: {booking[5]}")
    p.drawString(300, y, f"Date: {booking[6]}")
    y -= 40
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, "Patient Details:")
    y -= 25
    p.setFont("Helvetica", 12)
    p.drawString(50, y, f"Name: {booking[0]}")
    y -= 20
    p.drawString(50, y, f"Age: {booking[2]}")
    y -= 20
    p.drawString(50, y, f"Place: {booking[1]}")
    y -= 20
    p.drawString(50, y, f"Phone: {booking[3]}")
    y -= 20
    p.drawString(50, y, f"DOB: {booking[4]}")
    
    p.showPage()
    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"royal_clinic_booking_{booking_id}.pdf", mimetype='application/pdf')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
