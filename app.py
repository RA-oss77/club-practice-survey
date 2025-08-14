from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date, timedelta
import calendar

app = Flask(__name__)

# CORS設定を追加
CORS(app, resources={r"/*": {"origins": "*"}})

# SQLiteデータベース設定
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reservations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# モデル定義（予約データ）
class PracticeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_key = db.Column(db.String(20), nullable=False)  # "YYYY-M-D"
    user_name = db.Column(db.String(50), nullable=False)
    time_slot = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"<PracticeRequest {self.date_key} {self.user_name} {self.time_slot}>"

# モデル定義（時間枠データ）
class TimeSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_key = db.Column(db.String(20), nullable=False)
    slot = db.Column(db.String(50), nullable=False)

# DB作成
with app.app_context():
    db.create_all()

calendar.setfirstweekday(calendar.SUNDAY)

def get_default_slots(year, month, day):
    import datetime
    dt = datetime.date(year, month, day)
    if dt.weekday() == 5 or dt.weekday() == 6:  # 5:土, 6:日
        return ['12:30~14:30', '14:30~16:30']
    else:
        return ['〜16:50', '16:50〜18:00']

@app.route('/')
def index():
    today = date.today()
    year = today.year
    month = today.month
    cal = calendar.monthcalendar(year, month)
    month_names = ['1月', '2月', '3月', '4月', '5月', '6月', 
                  '7月', '8月', '9月', '10月', '11月', '12月']
    # 今月の残り日数を計算
    import calendar as calmod
    last_day = calmod.monthrange(year, month)[1]
    days_left = last_day - today.day
    calendars = [
        {
            'year': year,
            'month': month,
            'month_name': month_names[month-1],
            'calendar': cal
        }
    ]
    # 残り1週間以内なら来月分も追加
    if days_left < 7:
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year += 1
        next_cal = calendar.monthcalendar(next_year, next_month)
        calendars.append({
            'year': next_year,
            'month': next_month,
            'month_name': month_names[next_month-1],
            'calendar': next_cal
        })
   # 今日から2週間分
    valid_dates = {f"{(today + timedelta(days=i)).year}-{(today + timedelta(days=i)).month}-{(today + timedelta(days=i)).day}" for i in range(14)}

    
    # DBから予約データ取得
    practice_requests = {}
    booked_dates = set()
    all_requests = PracticeRequest.query.all()
    for req in all_requests:
        if req.date_key not in practice_requests:
            practice_requests[req.date_key] = {}
        practice_requests[req.date_key][req.user_name] = req.time_slot
        booked_dates.add(req.date_key)
    # DBから時間枠取得
    time_slots = {}
    all_slots = TimeSlot.query.all()
    for slot in all_slots:
        if slot.date_key not in time_slots:
            time_slots[slot.date_key] = []
        time_slots[slot.date_key].append(slot.slot)


    
    return render_template(
        'index.html',
        calendars=calendars,
        month=month_names[month-1],
        month_num=month,
        year=year,
        today=today,
        practice_requests=practice_requests,
        time_slots=time_slots,
        get_default_slots=get_default_slots,
        valid_dates=valid_dates,
        booked_dates=booked_dates
    )

@app.route('/admin')
def admin():
    today = date.today()
    week_dates = [(today + timedelta(days=i)) for i in range(14)]  # 2週間分
    practice_users = {}

    # DBから時間枠取得
    time_slots = {}
    all_slots = TimeSlot.query.all()
    for slot in all_slots:
        if slot.date_key not in time_slots:
            time_slots[slot.date_key] = []
        time_slots[slot.date_key].append(slot.slot)

    for d in week_dates:
        date_key = f"{d.year}-{d.month}-{d.day}"
        slots = time_slots.get(date_key, get_default_slots(d.year, d.month, d.day))
        users_per_slot = {slot: [] for slot in slots}
        
        # DBからこの日付の予約を取得
        requests = PracticeRequest.query.filter_by(date_key=date_key).all()
        for req in requests:
            if req.time_slot in users_per_slot:
                users_per_slot[req.time_slot].append(req.user_name)

        
        practice_users[date_key] = users_per_slot
    return render_template('admin.html', week_dates=week_dates, time_slots=time_slots, practice_users=practice_users, get_default_slots=get_default_slots)

@app.route('/get_time_slots/<int:year>/<int:month>/<int:day>')
def get_time_slots(year, month, day):
    date_key = f"{year}-{month}-{day}"
    slots = [s.slot for s in TimeSlot.query.filter_by(date_key=date_key).all()]
    if not slots:
        slots = get_default_slots(year, month, day)

    slot_users = {slot: [] for slot in slots}
    requests = PracticeRequest.query.filter_by(date_key=date_key).all()
    for req in requests:
        if req.time_slot in slot_users:
            slot_users[req.time_slot].append(req.user_name)

    return jsonify({
        'time_slots': [
            {'id': slot, 'label': slot, 'users': slot_users[slot]} for slot in slots
        ],
        'selected': None
    })

@app.route('/submit_practice', methods=['POST'])
def submit_practice():
    data = request.get_json()
    print(f"練習希望送信: {data}")  # デバッグ用
    date_key = f"{data['year']}-{data['month']}-{data['day']}"
    user_name = data.get('user_name')
    time_slot = data.get('time_slot')
    if not user_name or not time_slot:
        return jsonify({'status': 'error', 'message': '名前と時間帯は必須です'}), 400
    existing = PracticeRequest.query.filter_by(date_key=date_key, user_name=user_name).first()
    if existing:
        existing.time_slot = time_slot
    else:
        db.session.add(PracticeRequest(date_key=date_key, user_name=user_name, time_slot=time_slot))

    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/admin/update_time_slots', methods=['POST'])
def update_time_slots():
    data = request.get_json()
    date_str = data.get('date')  # 'YYYY-MM-DD'
    slots = data.get('slots', [])
    if not date_str or not isinstance(slots, list):
        return jsonify({'status': 'error', 'message': '不正なデータ'}), 400
    # ゼロ埋めなしのキーに変換
    y, m, d = [int(x) for x in date_str.split('-')]
    key = f'{y}-{m}-{d}'
    # 既存スロット削除して新規追加
    TimeSlot.query.filter_by(date_key=key).delete()
    for slot in slots:
        db.session.add(TimeSlot(date_key=key, slot=slot))

    db.session.commit()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    import os
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug, host=host, port=port) 