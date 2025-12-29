import pandas as pd
import numpy as np
import re
import os
from git_analyzer import load_week_range


def _split_filename_and_count(cell: str):
    """
    '<a href="...">path/to/file.py (3)</a>' 형태나 'path/to/file.py (3)' 형태에서
    파일명(anchor 유지)과 정수 커밋 수를 분리합니다.
    """
    if pd.isna(cell):
        return cell, None

    s = str(cell)
    href = None
    # href 추출 (있을 경우)
    m_href = re.search(r'href="([^"]+)"', s)
    if m_href:
        href = m_href.group(1)

    # 앵커 안에 '파일명 (숫자)' 형태
    m = re.search(r'>(.*?)\s*\((\d+)\)\s*</a>\s*$', s)
    if m:
        filename_text = m.group(1).strip()
        count = int(m.group(2))
        anchor = f'<a href="{href}" target="_blank">{filename_text}</a>' if href else filename_text
        return anchor, count

    # 일반 텍스트 '파일명 (숫자)' 형태
    m2 = re.search(r'^(.*?)\s*\((\d+)\)\s*$', s)
    if m2:
        filename_text = m2.group(1).strip()
        count = int(m2.group(2))
        anchor = f'<a href="{href}" target="_blank">{filename_text}</a>' if href else filename_text
        return anchor, count

    # 숫자를 못 찾으면 앵커 안의 텍스트만 파일명으로
    m3 = re.search(r'>(.*?)</a>', s)
    if m3:
        filename_text = m3.group(1).strip()
        anchor = f'<a href="{href}" target="_blank">{filename_text}</a>' if href else filename_text
        return anchor, None

    return s, None


def _parse_minutes(duration_str: str):
    """
    '50분' 형태의 문자열을 정수(분)로 변환합니다.
    """
    try:
        match = re.search(r'(\d+)', duration_str)
        if match:
            return int(match.group(1))
        return 0
    except:
        return 0


def save_dataframe_as_html(df, output_path="commit_summary.html", title="파일별 커밋 통계"):
    week_label, start_date, end_date = load_week_range()

    # 입력 df에 '파일명 (총 커밋 수)'가 있다면 '파일명', '총 커밋 수'로 분리
    if "파일명 (총 커밋 수)" in df.columns:
        filenames = []
        counts = []
        for val in df["파일명 (총 커밋 수)"]:
            name_anchor, cnt = _split_filename_and_count(val)
            filenames.append(name_anchor)
            counts.append(cnt if cnt is not None else 0)
        df["파일명"] = filenames
        df["총 커밋 수"] = pd.Series(counts, index=df.index).astype(int)
        df.drop(columns=["파일명 (총 커밋 수)"], inplace=True)
    else:
        if "파일명" in df.columns and "총 커밋 수" not in df.columns:
            df["총 커밋 수"] = 0

    # '총 커밋 수'에 대한 Z-score 계산 및 이상치 플래그 생성
    commit_counts = df["총 커밋 수"].to_numpy()
    mean_commit = np.mean(commit_counts)
    std_commit = np.std(commit_counts)
    if std_commit != 0:
        z_scores_commit = (commit_counts - mean_commit) / std_commit
    else:
        z_scores_commit = np.zeros(len(commit_counts))
    df["z_score_commit"] = np.round(z_scores_commit, 2)
    df['commit_count_is_outlier'] = z_scores_commit < -1.0
    df["z_score_commit_style"] = ""
    df.loc[df[
        'commit_count_is_outlier'], "z_score_commit_style"] = "color: red; text-decoration: underline; font-weight: bold;"

    # '평균 수정 라인 수'에 대한 Z-score 계산 및 이상치 플래그 생성
    avg_changes = df["평균 수정 라인 수 (+/-)"].apply(lambda x: float(x.split(' ')[0])).to_numpy()
    mean_changes = np.mean(avg_changes)
    std_changes = np.std(avg_changes)
    if std_changes != 0:
        z_scores_changes = (avg_changes - mean_changes) / std_changes
    else:
        z_scores_changes = np.zeros(len(avg_changes))
    df["z_score_changes"] = np.round(z_scores_changes, 2)
    df['avg_changes_is_outlier'] = z_scores_changes > 2.0
    df["z_score_changes_style"] = ""
    df.loc[df[
        'avg_changes_is_outlier'], "z_score_changes_style"] = "color: red; text-decoration: underline; font-weight: bold;"

    # 코드 유사도에 대한 이상치 플래그 생성 및 HTML 처리
    df['code_similarity_is_outlier'] = df['코드 유사도'].isna() | (df['코드 유사도'] < 85.0)

    # NaN 값과 85% 미만 값 모두에 동일한 스타일 적용
    df['code_similarity_html'] = df["코드 유사도"].astype(str) + "%"
    df.loc[df['코드 유사도'].isna(), 'code_similarity_html'] = "NaN%"
    df['code_similarity_style'] = ""
    df.loc[df[
        'code_similarity_is_outlier'], 'code_similarity_style'] = "color:red; font-weight:bold; text-decoration: underline;"

    # '코딩 시간'에 대한 Z-score 계산 및 이상치 플래그 생성
    coding_minutes = df["코딩 시간"].apply(_parse_minutes).to_numpy()
    mean_minutes = np.mean(coding_minutes)
    std_minutes = np.std(coding_minutes)
    if std_minutes != 0:
        z_scores_minutes = (coding_minutes - mean_minutes) / std_minutes
    else:
        z_scores_minutes = np.zeros(len(coding_minutes))
    df["z_score_minutes"] = np.round(z_scores_minutes, 2)
    df['coding_minutes_is_outlier'] = z_scores_minutes < -1.0
    df["z_score_minutes_style"] = ""
    df.loc[df[
        'coding_minutes_is_outlier'], "z_score_minutes_style"] = "color: red; font-weight: bold; text-decoration: underline;"

    # 새로운 평가 로직: 이상치 개수 기반
    df['outlier_count'] = df['commit_count_is_outlier'].astype(int) + \
                          df['avg_changes_is_outlier'].astype(int) + \
                          df['code_similarity_is_outlier'].astype(int) + \
                          df['coding_minutes_is_outlier'].astype(int)

    df['평가'] = 'success'
    df.loc[df['outlier_count'] >= 3, '평가'] = 'fail'
    df.loc[(df['outlier_count'] >= 1) & (df['outlier_count'] < 3), '평가'] = 'warning'

    df["result_color"] = df["평가"].map({
        "fail": "background-color: #ffdddd;",
        "warning": "background-color: #fffacc;",
        "success": "background-color: #ddffdd;"
    })

    df["최근 커밋일시(dt)"] = pd.to_datetime(df["최근 커밋일시"])
    df["week_label"] = df["최근 커밋일시(dt)"].apply(lambda d: week_label if start_date <= d <= end_date else "")
    df.drop(columns=["최근 커밋일시(dt)"], inplace=True)

    # '이름'과 'user'를 기준으로 정렬하여 그룹화 준비
    df = df.sort_values(by=["이름", "user"]).reset_index(drop=True)

    # 첫 번째 테이블 (파일별 상세 통계) HTML 생성
    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        table {{
            border-collapse: collapse;
            width: 100%;
            font-family: Arial, sans-serif;
            margin-bottom: 30px; /* 테이블 간 간격 추가 */
        }}
        th, td {{
            border: 1px solid #ccc;
            padding: 8px;
            text-align: center;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        td.filename-col {{
            text-align: left;
        }}
    </style>
    </head>
    <body>
    <h2>{title} (파일별)</h2>
    <table>
    <thead>
    <tr>
        <th>순번</th>
        <th>주차</th>
        <th>이름</th>
        <th>user</th>
        <th>파일명</th>
        <th>최근 커밋일시</th>
        <th>상태</th>
        <th>총 커밋 수 (Z-score)</th>
        <th>평균 수정 라인 수 (+/-) (Z-score)</th>
        <th>코드 유사도</th>
        <th>코딩 시간 (Z-score)</th>
        <th>평가</th>
    </tr>
    </thead>
    <tbody>
    """

    # '이름'과 'user'를 기준으로 그룹화하여 HTML 행 생성
    row_number = 1
    for (name, user), group in df.groupby(['이름', 'user']):
        rowspan = len(group)
        for idx, row in group.iterrows():
            html += "<tr>"
            # 첫 번째 행에만 순번, 주차, 이름, user 셀 병합
            if idx == group.index[0]:
                html += f"<td rowspan='{rowspan}'>{row_number}</td>"
                html += f"<td rowspan='{rowspan}'>{row['week_label']}</td>"
                html += f"<td rowspan='{rowspan}'>{row['이름']}</td>"
                html += f"<td rowspan='{rowspan}'>{row['user']}</td>"

            html += f"<td class='filename-col'>{row['파일명']}</td>"
            html += f"<td>{row['최근 커밋일시']}</td>"
            html += f"<td>{row['상태']}</td>"
            html += f"<td style='{row['z_score_commit_style']}'>{row['총 커밋 수']} ({row['z_score_commit']})</td>"
            html += f"<td style='{row['z_score_changes_style']}'>{row['평균 수정 라인 수 (+/-)']} ({row['z_score_changes']})</td>"
            html += f"<td style='{row['code_similarity_style']}'>{row['code_similarity_html']}</td>"
            html += f"<td style='{row['z_score_minutes_style']}'>{row['코딩 시간']} ({row['z_score_minutes']})</td>"
            html += f"<td style='{row['result_color']}'>{row['평가']}</td>"
            html += "</tr>"

        row_number += 1

    html += "</tbody></table>"

    # --- 두 번째 테이블 (사용자별 종합 통계) 생성 ---

    # 사용자별로 그룹화하여 파일 수, 평가별 개수 및 최근 커밋 일시가 같은 파일 개수 집계
    user_summary = df.groupby(['이름', 'user']).agg(
        total_files=('파일명', 'size'),
        success_count=('평가', lambda x: (x == 'success').sum()),
        warning_count=('평가', lambda x: (x == 'warning').sum()),
        fail_count=('평가', lambda x: (x == 'fail').sum()),
        latest_commit_file_count=('최근 커밋일시', lambda x: (x == x.mode().iloc[0]).sum())
    ).reset_index()

    # 비율 계산 및 스타일 적용
    user_summary['latest_commit_file_ratio'] = user_summary['latest_commit_file_count'] / user_summary['total_files']
    user_summary['latest_commit_style'] = np.where(user_summary['latest_commit_file_ratio'] > 0.1,
                                                   'background-color: #ffdddd;', '')

    html += f"""
    <h2>{title} (사용자별 종합)</h2>
    <table>
    <thead>
    <tr>
        <th>순번</th>
        <th>이름</th>
        <th>user</th>
        <th>조회한 파일의 총 갯수</th>
        <th>최근 커밋일시가 같은 파일 수</th>
        <th>success 수</th>
        <th>warning 수</th>
        <th>fail 수</th>
    </tr>
    </thead>
    <tbody>
    """

    for i, row in user_summary.iterrows():
        html += "<tr>"
        html += f"<td>{i + 1}</td>"
        html += f"<td>{row['이름']}</td>"
        html += f"<td>{row['user']}</td>"
        html += f"<td>{row['total_files']}</td>"
        html += f"<td style='{row['latest_commit_style']}'>{row['latest_commit_file_count']}</td>"
        html += f"<td>{row['success_count']}</td>"
        html += f"<td>{row['warning_count']}</td>"
        html += f"<td>{row['fail_count']}</td>"
        html += "</tr>"

    html += "</tbody></table></body></html>"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ HTML 파일 저장 완료: {output_path}")
