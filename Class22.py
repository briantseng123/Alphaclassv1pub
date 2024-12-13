import streamlit as st
from dataclasses import dataclass, asdict
from typing import List, Tuple
import json
import itertools
import pandas as pd
from io import StringIO

# 定義 Course 類別
@dataclass
class Course:
    name: str
    type: str  # '必修' 或 '選修'
    class_id: str
    credits: int
    priority: int  # 優先順序，1最低，5最高
    time_slots: List[Tuple[str, int]]
    must_select: bool = False
    temporarily_exclude: bool = False
    teacher: str = ""  # 授課老師
    notes: str = ""  # 備註

# 保存課程到 JSON
def save_courses_to_json(courses: List[Course]) -> str:
    return json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=4)

# 從 JSON 載入課程
def load_courses_from_json(uploaded_file) -> List[Course]:
    try:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        data = json.load(stringio)
        courses = []
        for item in data:
            course = Course(
                name=item['name'],
                type=item['type'],
                class_id=item['class_id'],
                credits=item['credits'],
                priority=item.get('priority', 3),
                time_slots=[tuple(ts) for ts in item['time_slots']],
                must_select=item.get('must_select', False),
                temporarily_exclude=item.get('temporarily_exclude', False),
                teacher=item.get('teacher', ""),
                notes=item.get('notes', "")
            )
            courses.append(course)
        return courses
    except Exception as e:
        st.error(f"載入失敗: {e}")
        return []

# 排課算法
def generate_schedules(courses: List[Course], required_courses: List[Course], elective_courses: List[Course],
                       max_schedules=1000):
    schedules = {}
    grouped_courses = {}

    # 提取被標記為必選的課程名稱
    must_select_names = set(c.name for c in required_courses if c.must_select)

    # 從課程列表中移除暫時排除的課程
    available_courses = [c for c in courses if not c.temporarily_exclude]

    # 確保所有必選課程名稱都有可選的課程
    for name in must_select_names:
        if not any(c.name == name for c in available_courses):
            st.error(f"必選課程 '{name}' 沒有可選的時間段或已被暫時排除。")
            return []

    # 分組課程，並將 must_select 的課程放在前面
    for c in available_courses:
        if c.name not in grouped_courses:
            grouped_courses[c.name] = []
        grouped_courses[c.name].append(c)

    # 將每組中的 must_select 課程優先排序
    for name, group in grouped_courses.items():
        grouped_courses[name] = sorted(group, key=lambda c: (not c.must_select, -c.priority))

    # 生成所有可能的課程組合
    course_names = list(grouped_courses.keys())
    course_options = [grouped_courses[n] for n in course_names]
    all_combinations = itertools.product(*course_options)

    count_generated = 0  # 計算已生成的排課方案數量

    for combo in all_combinations:
        if count_generated >= max_schedules:
            st.warning(f"已達到最大排課方案數量 ({max_schedules})，停止生成更多方案。")
            break

        # 確保該組合包含所有必選課程名稱中的至少一門課
        has_all_must_select = all(any(c.name == name for c in combo) for name in must_select_names)
        if not has_all_must_select:
            continue

        # 創建一個時間槽到課程列表的映射
        time_slot_map = {}
        for c in combo:
            for day, period in c.time_slots:
                key = (day, period)
                if key not in time_slot_map:
                    time_slot_map[key] = []
                time_slot_map[key].append(c)

        conflicts = []
        conflict_count = 0  # 計算衝堂數

        for (day, period), course_list in time_slot_map.items():
            if len(course_list) > 1:
                # 衝堂的時間槽
                conflicts.append((day, period, course_list))
                # 每個衝堂時間槽計算衝堂數為重疊課程數減一
                conflict_count += len(course_list) - 1

        total_credits = sum(c.credits for c in combo)
        req_credits = sum(c.credits for c in combo if c.type == '必修')
        ele_credits = sum(c.credits for c in combo if c.type == '選修')
        total_priority = sum(c.priority for c in combo)

        # 如果沒有衝堂，conflicts清單就設為 None
        if conflict_count == 0:
            conflicts = None

        # 統一結構 (combo, total_priority, total_credits, req_credits, ele_credits, conflicts, conflict_count)
        schedules.setdefault(conflict_count, []).append(
            (combo, total_priority, total_credits, req_credits, ele_credits, conflicts, conflict_count)
        )
        count_generated += 1

    # 將排課方案轉換為列表，並根據衝堂數排序
    sorted_conflict_counts = sorted(schedules.keys())
    for ccount in sorted_conflict_counts:
        schedules[ccount].sort(key=lambda x: (-x[1], -x[2]))  # 依優先順序總和降序，學分總數降序

    # 將所有方案平展為列表
    all_schedules = []
    for ccount in sorted_conflict_counts:
        all_schedules.extend(schedules[ccount])

    return all_schedules

# 顯示排課格子函數
def display_schedule_grid(combo: List[Course], conflicts=None):
    # 定義星期和堂課範圍
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    periods = list(range(1, 11))  # 1 到 10

    # 初始化 DataFrame
    schedule_df = pd.DataFrame("", index=periods, columns=days)

    # 填充課堂名稱
    for course in combo:
        for day, period in course.time_slots:
            if day in days and 1 <= period <= 10:
                if schedule_df.at[period, day]:
                    # 如果已經有課堂，表示有衝堂
                    schedule_df.at[period, day] += f", {course.name}({course.teacher})" if course.teacher else f", {course.name}"
                else:
                    schedule_df.at[period, day] = f"{course.name}({course.teacher})" if course.teacher else f"{course.name}"

    # 將空白單元格替換為 "-"
    schedule_df.replace("", "-", inplace=True)

    # 使用 pandas Styler 來設置表格樣式
    styled = schedule_df.style.applymap(
        lambda x: 'background-color: black; color: white; border: 1px solid white; text-align: center;'
    ).set_table_styles([
        {
            'selector': 'th',
            'props': [
                ('background-color', 'black'),
                ('color', 'white'),
                ('border', '1px solid white'),
                ('text-align', 'center'),
                ('padding', '5px')
            ]
        },
        {
            'selector': 'td',
            'props': [
                ('border', '1px solid white'),
                ('padding', '5px')
            ]
        },
        {
            'selector': 'table',
            'props': [
                ('background-color', 'black'),
                ('color', 'white'),
                ('border-collapse', 'collapse'),
                ('width', '100%')
            ]
        }
    ])

    # 將 Styler 轉換為 HTML
    html = styled.to_html()

    # 顯示表格
    st.markdown(html, unsafe_allow_html=True)

    # 如果有衝堂，顯示衝堂課程
    if conflicts:
        st.write("**衝堂課程:**")
        for day, period, overlapping_courses in conflicts:
            overlap_str = ', '.join(
                [f"{c.name}({c.teacher})" if c.teacher else f"{c.name}" for c in overlapping_courses]
            )
            st.write(f"- {day} {period}: {overlap_str}")

def main():
    st.set_page_config(page_title="排課助手", layout="wide")
    st.title("排課助手")

    # 初始化 session state
    if 'courses' not in st.session_state:
        st.session_state.courses = []

    if 'generated_schedules' not in st.session_state:
        st.session_state.generated_schedules = []  # 無衝堂
    if 'conflict_schedules' not in st.session_state:
        st.session_state.conflict_schedules = []  # 有衝堂

    # 初始化 time_slots
    if 'time_slots' not in st.session_state:
        st.session_state['time_slots'] = {'必修': [], '選修': []}

    # 側邊欄操作
    st.sidebar.header("操作選單")
    uploaded_file = st.sidebar.file_uploader("載入課程資料 (JSON)", type=["json"])
    if uploaded_file:
        loaded_courses = load_courses_from_json(uploaded_file)
        if loaded_courses:
            st.session_state.courses = loaded_courses
            st.sidebar.success(
                f"成功載入 {len(st.session_state.courses)} 門課程。")

    # 儲存課程資料
    if st.sidebar.button("儲存課程資料 (JSON)"):
        if not st.session_state.courses:
            st.sidebar.warning("目前沒有課程可以儲存。")
        else:
            json_data = save_courses_to_json(st.session_state.courses)
            st.sidebar.download_button(
                label="下載課程資料",
                data=json_data,
                file_name="courses.json",
                mime="application/json"
            )
            st.sidebar.success("課程資料已準備好下載。")

    # 主體分為三個部分：新增課程、課程列表、生成排課方案
    tabs = st.tabs(["新增課程", "課程列表", "生成排課方案"])

    # 新增課程
    with tabs[0]:
        st.subheader("新增課程")
        # 分為必修和選修
        course_types = ['必修', '選修']
        for course_type in course_types:
            with st.expander(f"新增 {course_type} 課程"):
                st.subheader(f"新增 {course_type} 課程")
                with st.form(key=f"add_course_form_{course_type}"):
                    name = st.text_input("課程名稱", key=f"{course_type}_name")
                    class_id = st.text_input("班級", key=f"{course_type}_class_id")
                    credits = st.number_input("學分數", min_value=1, step=1, key=f"{course_type}_credits")
                    priority = st.selectbox("優先順序", options=[1, 2, 3, 4, 5], index=0, key=f"{course_type}_priority")
                    teacher = st.text_input("授課老師", key=f"{course_type}_teacher")
                    notes = st.text_input("備註", key=f"{course_type}_notes")

                    st.markdown("### 上課時間")
                    col1, col2, col3 = st.columns([2, 2, 1])
                    day = col1.selectbox("星期", options=["Mon", "Tue", "Wed", "Thu", "Fri"], key=f"{course_type}_day")
                    period = col2.number_input("堂課", min_value=1, max_value=10, step=1, key=f"{course_type}_period")
                    add_time = col3.form_submit_button("添加時間")

                    # 顯示已添加的上課時間，並提供刪除選項
                    time_slots = st.session_state['time_slots'][course_type]
                    if add_time:
                        st.session_state['time_slots'][course_type].append((day, period))
                        st.success(f"已添加時間: {day} {period}")
                        st.rerun()

                    if time_slots:
                        st.write("已添加的上課時間:")
                        # 使用多選框來標記需要刪除的時間槽
                        delete_indices = []
                        for idx, (d, p) in enumerate(time_slots):
                            if st.checkbox(f"刪除 {d} {p}", key=f"del_{course_type}_{idx}"):
                                delete_indices.append(idx)

                        # 提交刪除
                        if st.form_submit_button("刪除選定時間槽"):
                            for idx in sorted(delete_indices, reverse=True):
                                del st.session_state['time_slots'][course_type][idx]
                            st.success("已刪除選定的時間槽。")
                            st.rerun()

                    must_select = st.checkbox("必選", key=f"{course_type}_must_select")
                    temporarily_exclude = st.checkbox("暫時排除", key=f"{course_type}_temporarily_exclude")

                    submit = st.form_submit_button("新增課程")
                    if submit:
                        if not name or not class_id or not time_slots:
                            st.error("請確保所有欄位都已填寫並添加上課時間。")
                        else:
                            # 檢查重複課程
                            duplicate = False
                            for c in st.session_state.courses:
                                if c.name == name and c.class_id == class_id:
                                    duplicate = True
                                    break
                            if duplicate:
                                st.error(f"課程 '{name}' 已存在於班級 {class_id}。")
                            else:
                                new_course = Course(
                                    name=name,
                                    type=course_type,
                                    class_id=class_id,
                                    credits=int(credits),
                                    priority=int(priority),
                                    time_slots=time_slots.copy(),
                                    must_select=must_select,
                                    temporarily_exclude=temporarily_exclude,
                                    teacher=teacher,
                                    notes=notes
                                )
                                st.session_state.courses.append(new_course)
                                st.success(f"課程 '{name}' 已新增。")
                                st.session_state['time_slots'][course_type] = []  # 清空時間槽
                                st.rerun()

        st.markdown("---")

    # 課程列表（使用 st.data_editor）
    with tabs[1]:
        st.subheader("課程列表")

        st.markdown("**必選**：同一堂課中，優先以必選為是的課程進行排序")
        st.markdown("**暫時排除**：暫時不將該課程納入生成方案")

        st.markdown("**課程刪除方法**: 點擊課程的左側的欄位後，表格的右上角有垃圾桶")
        st.markdown("**課程編輯方法**: 雙擊想要更動的點，即可編輯")

        if st.session_state.courses:
            # 將課程資料轉換為 DataFrame
            df = pd.DataFrame([{
                '名稱': c.name,
                '類型': c.type,
                '班級': c.class_id,
                '學分': c.credits,
                '優先順序': c.priority,
                '授課老師': c.teacher,
                '備註': c.notes,
                '時間槽': '; '.join([f"{d} {p}" for d, p in c.time_slots]),
                '必選': '是' if c.must_select else '否',
                '暫時排除': '是' if c.temporarily_exclude else '否'
            } for c in st.session_state.courses])

            # 使用 st.data_editor 進行課程編輯
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                key='course_list',
                hide_index=True,
                column_config={
                    "必選": st.column_config.SelectboxColumn(options=["是", "否"]),
                    "暫時排除": st.column_config.SelectboxColumn(options=["是", "否"])
                }
            )

            # 按下「更新課程」按鈕後更新 session state
            if st.button("更新課程"):
                updated_courses = []
                for _, row in edited_df.iterrows():
                    # 檢查必填欄位
                    if not row['名稱'] or not row['班級'] or not row['時間槽']:
                        st.error("請確保所有課程的名稱、班級和時間槽都已填寫。")
                        st.stop()

                    # 解析時間槽
                    time_slots = []
                    for ts in row['時間槽'].split(';'):
                        parts = ts.strip().split()
                        if len(parts) != 2:
                            st.error(f"時間槽格式錯誤: '{ts}'")
                            st.stop()
                        day, period = parts
                        try:
                            period = int(period)
                            time_slots.append((day, period))
                        except ValueError:
                            st.error(f"堂課應為數字: '{ts}'")
                            st.stop()

                    updated_course = Course(
                        name=row['名稱'],
                        type=row['類型'],
                        class_id=row['班級'],
                        credits=int(row['學分']),
                        priority=int(row['優先順序']),
                        time_slots=time_slots,
                        must_select=(row['必選'] == '是'),
                        temporarily_exclude=(row['暫時排除'] == '是'),
                        teacher=row['授課老師'],
                        notes=row['備註']
                    )
                    updated_courses.append(updated_course)

                st.session_state.courses = updated_courses
                st.success("課程列表已更新。")
                st.rerun()

        else:
            st.info("目前沒有課程。")

    # 生成排課方案
    with tabs[2]:
        st.subheader("生成排課方案")

        st.markdown("---")

        # 排課方案排序選項
        st.header("排課方案排序")
        sort_option = st.radio(
            "選擇排序方式",
            options=[
                "先衝堂數量少到多，接著優先順序總和多到少",
                "先優先順序總和多到少，接著衝堂數量少到多"
            ],
            index=0
        )

        if st.button("套用排序"):
            if st.session_state.generated_schedules or st.session_state.conflict_schedules:
                # 定義排序函數
                def sort_key(schedule):
                    # schedule: (combo, total_priority, total_credits, req_credits, ele_credits, conflicts, conflict_count)
                    conflict_count = schedule[6]
                    total_priority = schedule[1]
                    total_credits = schedule[2]

                    if sort_option == "先衝堂數量少到多，接著優先順序總和多到少":
                        return (conflict_count, -total_priority)
                    else:
                        return (-total_priority, conflict_count)

                # 排序方案
                st.session_state.generated_schedules.sort(key=sort_key)
                st.session_state.conflict_schedules.sort(key=sort_key)
                st.success("已套用排序。")
                st.rerun()
            else:
                st.warning("目前沒有排課方案可供排序。")

        st.markdown("---")

        # 按下「生成排課方案」按鈕後生成方案
        if st.button("生成排課方案"):
            if not st.session_state.courses:
                st.warning("目前沒有課程可以排課。")
            else:
                required_courses = [c for c in st.session_state.courses if c.type == '必修']
                elective_courses = [c for c in st.session_state.courses if c.type == '選修']

                if not required_courses:
                    st.warning("沒有必修課程，無法進行排課。")
                else:
                    with st.spinner("正在生成排課方案，請稍候..."):
                        all_schedules = generate_schedules(st.session_state.courses, required_courses, elective_courses)
                    if not all_schedules:
                        st.error("無法生成任何排課方案。")
                    else:
                        conflict_free = [s for s in all_schedules if s[6] == 0]
                        conflict_yes = [s for s in all_schedules if s[6] > 0]

                        # 定義排序函數
                        def sort_key_generated(s):
                            conflict_count = s[6]
                            total_priority = s[1]
                            total_credits = s[2]

                            if sort_option == "先衝堂數量少到多，接著優先順序總和多到少":
                                return (conflict_count, -total_priority)
                            else:
                                return (-total_priority, conflict_count)

                        # 排序方案
                        conflict_free.sort(key=sort_key_generated)
                        conflict_yes.sort(key=sort_key_generated)

                        st.session_state.generated_schedules = conflict_free
                        st.session_state.conflict_schedules = conflict_yes

                        st.success("排課方案已生成。")
                        st.rerun()

        # 顯示排課方案
        if st.session_state.generated_schedules or st.session_state.conflict_schedules:
            st.markdown("### 不衝堂方案")
            if st.session_state.generated_schedules:
                for i, (combo, tp, tc, rc, ec, cf, ccount) in enumerate(st.session_state.generated_schedules, start=1):
                    with st.expander(f"方案 {i} (優先順序總和: {tp})"):
                        st.write(f"**學分總數**: {tc}學分 (必修: {rc}學分, 選修: {ec}學分)")
                        for c in combo:
                            ts_str = '; '.join([f"{d} {p}" for d, p in c.time_slots])
                            teacher_info = f"授課老師: {c.teacher}" if c.teacher else "授課老師: 未指定"
                            st.write(
                                f"- **{c.name}** ({c.type}) 班級: {c.class_id} {c.credits}學分 優先順序: {c.priority} {teacher_info} 時間: {ts_str}")
                        display_schedule_grid(combo)
            else:
                st.write("無不衝堂的排課方案。")

            st.markdown("### 有衝堂方案")
            if st.session_state.conflict_schedules:
                for i, (combo, tp, tc, rc, ec, cf, ccount) in enumerate(st.session_state.conflict_schedules, start=1):
                    with st.expander(f"方案 {i} (優先順序總和: {tp}, 衝堂數: {ccount})"):
                        st.write(f"**學分總數**: {tc}學分 (必修: {rc}學分, 選修: {ec}學分)")
                        for c in combo:
                            ts_str = '; '.join([f"{d} {p}" for d, p in c.time_slots])
                            teacher_info = f"授課老師: {c.teacher}" if c.teacher else "授課老師: 未指定"
                            st.write(f"- **{c.name}** ({c.type}) 班級: {c.class_id} {c.credits}學分 優先順序: {c.priority} {teacher_info} 時間: {ts_str}")

                        if cf:
                            st.write("**衝堂課程:**")
                            for day, period, overlapping_courses in cf:
                                overlap_str = ', '.join(
                                    [f"{c.name}(班:{c.class_id})" for c in overlapping_courses]
                                )
                                st.write(f"- {day} {period}: {overlap_str}")

                        display_schedule_grid(combo, conflicts=cf)
            else:
                st.write("目前無有衝堂方案。")
        else:
            st.info("請先生成排課方案。")

if __name__ == "__main__":
    main()

