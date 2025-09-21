from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date, timedelta
import calendar
import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR

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
    band_name = db.Column(db.String(100), nullable=False)  # バンド名フィールドを追加
    time_slot = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"<PracticeRequest {self.date_key} {self.user_name} {self.band_name} {self.time_slot}>"

# モデル定義（時間枠データ）
class TimeSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_key = db.Column(db.String(20), nullable=False)
    slot = db.Column(db.String(50), nullable=False)

# モデル定義（時間枠変更の一時保存）
class TimeSlotChange(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_key = db.Column(db.String(20), nullable=False)
    slot = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# DB作成
try:
    with app.app_context():
        db.create_all()
        
        # 初期時間帯を設定（既存のデータがない場合のみ）
        existing_slots = TimeSlot.query.first()
        if not existing_slots:
            # 今日を含む週の日曜日を計算
            today = date.today()
            days_since_sunday = today.weekday() + 1  # 月曜日=0なので+1して日曜日=0にする
            if days_since_sunday == 7:  # 日曜日の場合は0にする
                days_since_sunday = 0
            current_week_sunday = today - timedelta(days=days_since_sunday)
            
            # 3週間分の日曜日から土曜日まで（21日間）にデフォルト時間帯を設定
            for week in range(3):  # 3週間
                week_start = current_week_sunday + timedelta(weeks=week)
                for day in range(7):  # 日曜日から土曜日まで
                    current_date = week_start + timedelta(days=day)
                    date_key = f"{current_date.year}-{current_date.month}-{current_date.day}"
                    default_slots = get_default_slots(current_date.year, current_date.month, current_date.day)
                    
                    for slot in default_slots:
                        db.session.add(TimeSlot(date_key=date_key, slot=slot))
            
            db.session.commit()
            print("初期時間帯を設定しました")
        
        print("データベースが正常に初期化されました")
except Exception as e:
    print(f"データベース初期化でエラーが発生しました: {e}")

calendar.setfirstweekday(calendar.SUNDAY)

# スケジューラー初期化
scheduler = BackgroundScheduler()

# スケジューラーのエラーハンドリング
def scheduler_error_handler(job_id, exception):
    print(f"スケジューラーエラー (Job ID: {job_id}): {exception}")

scheduler.add_listener(scheduler_error_handler, EVENT_JOB_ERROR)

def apply_time_slot_changes():
    """毎週日曜日19:00に時間帯変更を反映する関数"""
    with app.app_context():
        try:
            # 時間帯変更の一時保存データを取得
            changes = TimeSlotChange.query.all()
            
            if changes:
                # 日付ごとにグループ化
                changes_by_date = {}
                for change in changes:
                    if change.date_key not in changes_by_date:
                        changes_by_date[change.date_key] = []
                    changes_by_date[change.date_key].append(change.slot)
                
                # 各日付の時間帯を更新
                for date_key, slots in changes_by_date.items():
                    # 既存の時間帯を削除
                    TimeSlot.query.filter_by(date_key=date_key).delete()
                    
                    # 新しい時間帯を追加（空のマーカーがある場合は何も追加しない）
                    for slot in slots:
                        if slot != '__EMPTY_SLOTS__':
                            db.session.add(TimeSlot(date_key=date_key, slot=slot))
                
                # 一時保存データを削除
                TimeSlotChange.query.delete()
                
                db.session.commit()
                print(f"時間帯変更を反映しました: {len(changes)}件")
            else:
                print("反映する時間帯変更はありません")
            
            # 新しい週のデフォルト時間帯を設定
            today = date.today()
            # 3週間後の日曜日から土曜日まで（7日間）の時間帯を設定
            three_weeks_later = today + timedelta(weeks=3)
            days_since_sunday = three_weeks_later.weekday() + 1
            if days_since_sunday == 7:
                days_since_sunday = 0
            week_start = three_weeks_later - timedelta(days=days_since_sunday)
            
            for day in range(7):  # 日曜日から土曜日まで
                current_date = week_start + timedelta(days=day)
                date_key = f"{current_date.year}-{current_date.month}-{current_date.day}"
                
                # 既存の時間帯がない場合のみデフォルト時間帯を設定
                existing = TimeSlot.query.filter_by(date_key=date_key).first()
                if not existing:
                    default_slots = get_default_slots(current_date.year, current_date.month, current_date.day)
                    for slot in default_slots:
                        db.session.add(TimeSlot(date_key=date_key, slot=slot))
            
            db.session.commit()
            print("新しい週のデフォルト時間帯を設定しました")
                
        except Exception as e:
            print(f"時間帯変更の反映でエラーが発生しました: {e}")
            db.session.rollback()

# 毎週日曜日19:00にスケジュール設定
scheduler.add_job(
    func=apply_time_slot_changes,
    trigger=CronTrigger(day_of_week=6, hour=19, minute=0),  # 日曜日=6, 19:00
    id='weekly_time_slot_update',
    name='週次時間帯更新',
    replace_existing=True
)

# スケジューラー開始
try:
    scheduler.start()
    print("スケジューラーが正常に開始されました")
except Exception as e:
    print(f"スケジューラーの開始でエラーが発生しました: {e}")

def get_default_slots(year, month, day):
    dt = date(year, month, day)
    if dt.weekday() == 5 or dt.weekday() == 6:  # 5:土, 6:日
        return ['12:30~14:30', '14:30~16:30']
    else:
        return ['〜16:50', '16:50〜18:00']

@app.route('/', methods=['GET', 'HEAD'])
def index():
    try:
        # HEADリクエストの場合は空のレスポンスを返す
        if request.method == 'HEAD':
            return '', 200
        
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
        # 残り2週間以内なら来月分も追加
        if days_left < 14:
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
        # 今日を含む週の日曜日を計算
        days_since_sunday = today.weekday() + 1  # 月曜日=0なので+1して日曜日=0にする
        if days_since_sunday == 7:  # 日曜日の場合は0にする
            days_since_sunday = 0
        current_week_sunday = today - timedelta(days=days_since_sunday)
        
        # 2週間分の日曜日から土曜日まで（14日間）
        valid_dates = set()
        for week in range(2):  # 2週間
            week_start = current_week_sunday + timedelta(weeks=week)
            for day in range(7):  # 日曜日から土曜日まで
                current_date = week_start + timedelta(days=day)
                valid_dates.add(f"{current_date.year}-{current_date.month}-{current_date.day}")

        
        # DBから予約データ取得
        practice_requests = {}
        booked_dates = set()
        try:
            all_requests = PracticeRequest.query.all()
            for req in all_requests:
                if req.date_key not in practice_requests:
                    practice_requests[req.date_key] = {}
                practice_requests[req.date_key][req.user_name] = {
                    'time_slot': req.time_slot,
                    'band_name': req.band_name
                }
                booked_dates.add(req.date_key)
        except Exception as e:
            print(f"予約データ取得でエラー: {e}")
            practice_requests = {}
            booked_dates = set()
            
        # DBから時間枠取得
        time_slots = {}
        try:
            all_slots = TimeSlot.query.all()
            for slot in all_slots:
                if slot.date_key not in time_slots:
                    time_slots[slot.date_key] = []
                time_slots[slot.date_key].append(slot.slot)
        except Exception as e:
            print(f"時間枠データ取得でエラー: {e}")
            time_slots = {}

        
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
    except Exception as e:
        print(f"index関数でエラーが発生しました: {e}")
        return f"エラーが発生しました: {str(e)}", 500

@app.route('/admin')
def admin():
    today = date.today()
    # 今日を含む週の日曜日を計算
    days_since_sunday = today.weekday() + 1  # 月曜日=0なので+1して日曜日=0にする
    if days_since_sunday == 7:  # 日曜日の場合は0にする
        days_since_sunday = 0
    current_week_sunday = today - timedelta(days=days_since_sunday)
    
    # 3週間分の日曜日から土曜日まで（21日間）
    week_dates = []
    week_labels = ['今週', '来週', '再来週']
    for week in range(3):  # 3週間
        week_start = current_week_sunday + timedelta(weeks=week)
        for day in range(7):  # 日曜日から土曜日まで
            current_date = week_start + timedelta(days=day)
            # 日付オブジェクトに週ラベル情報を辞書として追加
            date_info = {
                'date': current_date,
                'week_label': week_labels[week] if day == 0 else None
            }
            week_dates.append(date_info)
    practice_users = {}

    # DBから時間枠取得
    time_slots = {}
    all_slots = TimeSlot.query.all()
    for slot in all_slots:
        if slot.date_key not in time_slots:
            time_slots[slot.date_key] = []
        time_slots[slot.date_key].append(slot.slot)
    
    # 一時保存された時間帯変更を取得
    pending_changes = {}
    all_changes = TimeSlotChange.query.all()
    for change in all_changes:
        if change.date_key not in pending_changes:
            pending_changes[change.date_key] = []
        # 空のマーカーの場合は空のリストとして処理
        if change.slot == '__EMPTY_SLOTS__':
            pending_changes[change.date_key] = []
        else:
            pending_changes[change.date_key].append(change.slot)

    for d_info in week_dates:
        d = d_info['date']  # 実際の日付オブジェクトを取得
        date_key = f"{d.year}-{d.month}-{d.day}"
        slots = time_slots.get(date_key, [])
        users_per_slot = {slot: [] for slot in slots}
        
        # DBからこの日付の予約を取得
        requests = PracticeRequest.query.filter_by(date_key=date_key).all()
        for req in requests:
            if req.time_slot in users_per_slot:
                # 予約者名とバンド名を含むオブジェクトを作成
                user_info = {
                    'name': req.user_name,
                    'band_name': req.band_name
                }
                users_per_slot[req.time_slot].append(user_info)

        
        practice_users[date_key] = users_per_slot
    
    # 次回反映予定時刻を計算
    next_sunday = current_week_sunday + timedelta(weeks=1)
    next_update_time = datetime.combine(next_sunday, datetime.min.time().replace(hour=19, minute=0))
    
    return render_template('admin.html', 
                         week_dates=week_dates, 
                         time_slots=time_slots, 
                         practice_users=practice_users, 
                         get_default_slots=get_default_slots,
                         pending_changes=pending_changes,
                         next_update_time=next_update_time)

@app.route('/get_time_slots/<int:year>/<int:month>/<int:day>')
def get_time_slots(year, month, day):
    date_key = f"{year}-{month}-{day}"
    slots = [s.slot for s in TimeSlot.query.filter_by(date_key=date_key).all()]
    # デフォルト時間帯のフォールバックを削除 - 空の場合は空のまま返す

    slot_users = {slot: [] for slot in slots}
    requests = PracticeRequest.query.filter_by(date_key=date_key).all()
    for req in requests:
        if req.time_slot in slot_users:
            # 予約者名とバンド名を含むオブジェクトを作成
            user_info = {
                'name': req.user_name,
                'band_name': req.band_name
            }
            slot_users[req.time_slot].append(user_info)

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
    band_name = data.get('band_name')  # バンド名を取得
    time_slot = data.get('time_slot')
    if not user_name or not band_name or not time_slot:
        return jsonify({'status': 'error', 'message': '名前、バンド名、時間帯は必須です'}), 400
    existing = PracticeRequest.query.filter_by(date_key=date_key, user_name=user_name).first()
    if existing:
        existing.time_slot = time_slot
        existing.band_name = band_name  # バンド名も更新
    else:
        db.session.add(PracticeRequest(date_key=date_key, user_name=user_name, band_name=band_name, time_slot=time_slot))

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
    
    # 既存の一時保存データを削除
    TimeSlotChange.query.filter_by(date_key=key).delete()
    
    # 新しい時間帯を一時保存（空の配列の場合も処理）
    if slots:
        for slot in slots:
            db.session.add(TimeSlotChange(date_key=key, slot=slot))
    else:
        # 空の配列の場合、特別なマーカーを保存して削除予定であることを記録
        db.session.add(TimeSlotChange(date_key=key, slot='__EMPTY_SLOTS__'))

    db.session.commit()
    return jsonify({'status': 'success', 'message': '時間帯変更を一時保存しました。毎週日曜日19:00に反映されます。'})

@app.route('/admin/apply_changes_now', methods=['POST'])
def apply_changes_now():
    """管理者による即時更新"""
    try:
        # 時間帯変更の一時保存データを取得
        changes = TimeSlotChange.query.all()
        
        if not changes:
            return jsonify({'status': 'info', 'message': '反映する変更がありません。'})
        
        # 日付ごとにグループ化
        changes_by_date = {}
        for change in changes:
            if change.date_key not in changes_by_date:
                changes_by_date[change.date_key] = []
            changes_by_date[change.date_key].append(change.slot)
        
        # 各日付の時間帯を更新
        for date_key, slots in changes_by_date.items():
            # 既存の時間帯を削除
            TimeSlot.query.filter_by(date_key=date_key).delete()
            
            # 新しい時間帯を追加（空のマーカーがある場合は何も追加しない）
            for slot in slots:
                if slot != '__EMPTY_SLOTS__':
                    db.session.add(TimeSlot(date_key=date_key, slot=slot))
        
        # 一時保存データを削除
        TimeSlotChange.query.delete()
        
        db.session.commit()
        
        print(f"管理者による即時更新: {len(changes)}件の変更を反映しました")
        return jsonify({
            'status': 'success', 
            'message': f'{len(changes_by_date)}日分の時間帯変更を即座に反映しました。'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"即時更新でエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': f'更新に失敗しました: {str(e)}'}), 500

@app.route('/admin/initialize_default_slots', methods=['POST'])
def initialize_default_slots():
    """管理者による初期時間帯設定"""
    try:
        # 今日を含む週の日曜日を計算
        today = date.today()
        days_since_sunday = today.weekday() + 1  # 月曜日=0なので+1して日曜日=0にする
        if days_since_sunday == 7:  # 日曜日の場合は0にする
            days_since_sunday = 0
        current_week_sunday = today - timedelta(days=days_since_sunday)
        
        # 3週間分の日曜日から土曜日まで（21日間）にデフォルト時間帯を設定
        count = 0
        for week in range(3):  # 3週間
            week_start = current_week_sunday + timedelta(weeks=week)
            for day in range(7):  # 日曜日から土曜日まで
                current_date = week_start + timedelta(days=day)
                date_key = f"{current_date.year}-{current_date.month}-{current_date.day}"
                
                # 既存の時間帯がない場合のみデフォルト時間帯を設定
                existing = TimeSlot.query.filter_by(date_key=date_key).first()
                if not existing:
                    default_slots = get_default_slots(current_date.year, current_date.month, current_date.day)
                    for slot in default_slots:
                        db.session.add(TimeSlot(date_key=date_key, slot=slot))
                    count += 1
        
        db.session.commit()
        
        if count > 0:
            print(f"管理者による初期時間帯設定: {count}日分を設定しました")
            return jsonify({
                'status': 'success', 
                'message': f'{count}日分のデフォルト時間帯を設定しました。'
            })
        else:
            return jsonify({
                'status': 'info', 
                'message': 'すべての日付に時間帯が既に設定されています。'
            })
        
    except Exception as e:
        db.session.rollback()
        print(f"初期時間帯設定でエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': f'設定に失敗しました: {str(e)}'}), 500

if __name__ == '__main__':
    import os
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug, host=host, port=port) 