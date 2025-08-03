from flask import Flask, render_template, jsonify, request
from datetime import datetime, date, timedelta
import calendar

app = Flask(__name__)

# { '2024-06-01': {'taro': 'before_17', 'hanako': '17_to_18'} }
practice_requests = {}
# 日付ごとの時間帯リスト（初期値は空）
time_slots = {}
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
    # 今日から2週間分の日付リスト
    valid_dates = set()
    for i in range(14):
        d = today + timedelta(days=i)
        valid_dates.add(f"{d.year}-{d.month}-{d.day}")
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
        valid_dates=valid_dates
    )

@app.route('/admin')
def admin():
    today = date.today()
    week_dates = [(today + timedelta(days=i)) for i in range(14)]  # 2週間分
    # 各日付・時間帯ごとの予約者リストを作成
    practice_users = {}
    for d in week_dates:
        date_key = f"{d.year}-{d.month}-{d.day}"
        slots = time_slots.get(date_key, get_default_slots(d.year, d.month, d.day))
        users_per_slot = {slot: [] for slot in slots}
        if date_key in practice_requests:
            for name, slot in practice_requests[date_key].items():
                if slot in users_per_slot:
                    users_per_slot[slot].append(name)
        practice_users[date_key] = users_per_slot
    return render_template('admin.html', week_dates=week_dates, time_slots=time_slots, practice_users=practice_users, get_default_slots=get_default_slots)

@app.route('/get_time_slots/<int:year>/<int:month>/<int:day>')
def get_time_slots(year, month, day):
    date_key = f"{year}-{month}-{day}"
    slots = time_slots.get(date_key, get_default_slots(year, month, day))
    slot_users = {slot: [] for slot in slots}
    if date_key in practice_requests:
        for name, slot in practice_requests[date_key].items():
            if slot in slot_users:
                slot_users[slot].append(name)
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
    if date_key not in practice_requests:
        practice_requests[date_key] = {}
    practice_requests[date_key][user_name] = time_slot
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
    time_slots[key] = slots
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000) 