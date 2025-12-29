import requests
import pandas as pd
import time
import re
import os
import difflib
from datetime import datetime, timedelta


class RepoNotFoundError(ValueError):
    pass


class RepoPermissionError(PermissionError):
    pass


def extract_repo_info(url, token=None):
    """
    GitHub 저장소 URL을 파싱하고, GitHub API로 실제 존재/권한 여부를 즉시 검증합니다.
    - 존재하지 않으면 RepoNotFoundError
    - 권한/인증 문제면 RepoPermissionError
    - 네트워크/기타 API 오류면 RuntimeError/ConnectionError
    """
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise ValueError("잘못된 GitHub 저장소 주소입니다. 예: https://github.com/owner/repo")

    owner, repo = match.group(1), match.group(2)
    # 뒤에 .git 이나 슬래시 등이 붙은 경우 방어
    repo = repo.rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
    except requests.RequestException as e:
        raise ConnectionError(f"GitHub API 연결 실패: {e}")

    if resp.status_code == 404:
        raise RepoNotFoundError(f"존재하지 않는 저장소입니다: {owner}/{repo}. URL을 확인하세요.")
    elif resp.status_code in (401, 403):
        # 403은 rate limit 또는 private 접근 거절일 수 있음
        msg = ""
        try:
            msg = resp.json().get("message", "")
        except Exception:
            pass
        if "rate limit" in msg.lower():
            raise RepoPermissionError("GitHub API rate limit을 초과했습니다. 잠시 후 다시 시도하거나 토큰을 사용하세요.")
        raise RepoPermissionError("권한이 없거나 private 저장소입니다. Personal Access Token과 접근 권한을 확인하세요.")
    elif resp.status_code != 200:
        snippet = ""
        try:
            snippet = resp.text[:200]
        except Exception:
            pass
        raise RuntimeError(f"GitHub API 오류 (status {resp.status_code}): {snippet}")

    return owner, repo


def calculate_result(count):
    if count == 1:
        return "fail"
    elif 2 <= count < 5:
        return "warning"
    else:
        return "success"


def fetch_loc(repo_owner, repo_name, branch, filename, headers):
    raw_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/{filename}"
    try:
        resp = requests.get(raw_url, headers=headers)
        if resp.status_code == 200:
            return resp.text.count("\n") + 1
        else:
            return None
    except:
        return None

def format_python_code(code_string: str) -> str:
    """Python 코드를 표준 스타일로 일괄 포맷팅합니다.

    우선 isort로 import를 정렬하고, 그 다음 black으로 코드 스타일을 맞춥니다.
    (환경에 isort/black이 없으면 원본 코드를 그대로 반환합니다.)
    """
    formatted = code_string

    # 1) isort
    try:
        import isort  # type: ignore

        formatted = isort.code(formatted)
    except Exception:
        pass

    # 2) black
    try:
        import black  # type: ignore

        formatted = black.format_file_contents(
            formatted, fast=False, mode=black.FileMode()
        )
    except Exception:
        pass

    return formatted


def calculate_similarity(local_code: str, remote_code: str) -> float:
    """
        포맷팅된 Python 코드의 유사도를 계산합니다.
        """
    # 1. 비교할 두 코드를 먼저 포맷팅합니다.
    formatted_local_code = format_python_code(local_code)
    formatted_remote_code = format_python_code(remote_code)

    # 2. 포맷팅된 코드를 SequenceMatcher로 비교합니다.
    matcher = difflib.SequenceMatcher(None, formatted_local_code, formatted_remote_code)

    # 3. 유사도 점수를 반환합니다.
    return round(matcher.ratio() * 100, 2)


def fetch_similarity(
    repo_owner,
    repo_name,
    branch,
    filename,
    headers,
    local_base_dir=".",
    directory_prefix="",
):
    """로컬 코드와 GitHub raw 코드(동일 파일)의 유사도를 계산합니다.

    - directory_prefix: GitHub 상의 경로 prefix(예: "lib/")를 로컬 경로에서 제거할 때 사용
    - local_base_dir: 로컬에서 repo를 둔 기준 디렉토리
    """
    rel_path = filename
    if directory_prefix and rel_path.startswith(directory_prefix):
        rel_path = rel_path[len(directory_prefix) :]

    local_path = os.path.join(local_base_dir, rel_path.lstrip("/"))
    if not os.path.exists(local_path):
        return None
    try:
        with open(local_path, "r", encoding="utf-8") as f:
            local_code = f.read()
        raw_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/{filename}"
        resp = requests.get(raw_url, headers=headers)
        if resp.status_code == 200:
            remote_code = resp.text
            return calculate_similarity(local_code, remote_code)
        else:
            return None
    except:
        return None


def calculate_duration(start_time, end_time):
    duration = end_time - start_time
    total_minutes = int(duration.total_seconds() / 60)
    return f"{total_minutes}분"


def load_week_range(file_path="week_information.txt"):
    with open(file_path, "r", encoding="utf-8") as f:
        line = f.readline().strip()
        label, start_str, end_str = line.split(",")
        start = datetime.strptime(start_str.strip(), "%Y-%m-%d")
        end = datetime.strptime(end_str.strip(), "%Y-%m-%d")
        return label, start, end


def analyze_commits(github_url, token, username, directory="", branch="main", start_date=None, end_date=None,
                    exclude_first_commit=False, user_actual_name=None):
    repo_owner, repo_name = extract_repo_info(github_url, token)
    week_label, start_filter, end_filter = load_week_range()

    github_directory = ""

    if not directory:
        directory = week_label
        if directory and not directory.endswith("/"):
            directory += "/"

    base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 1차 시도: GitHub username으로 검색
    params = {
        "per_page": 100,
        "author": username
    }
    raw_data = _fetch_commits(base_url, headers, params, github_directory, start_filter, end_filter, username)

    # 2차 시도: 1차 시도에서 결과가 없으면 전체 커밋을 가져와 commit author 이름으로 필터링
    if not raw_data:
        print(f"⚠️ GitHub username '{username}'으로 커밋을 찾을 수 없습니다. Git commit author 이름으로 재시도합니다.")
        params = {"per_page": 100}  # author 필터 제거
        raw_data = _fetch_commits(base_url, headers, params, github_directory, start_filter, end_filter, username)

    if not raw_data:
        print(f"⚠️ No commits found in directory '{github_directory}' for user '{username}' in selected week.")
        return pd.DataFrame()

    df = pd.DataFrame(raw_data)

    if exclude_first_commit:
        df["rank"] = df.groupby("filename")["date"].rank(method="first")
        df = df[~((df["rank"] == 1) & (df.groupby("filename")["filename"].transform("count") > 1))]
        df.drop(columns=["rank"], inplace=True)

    grouped_time = df.groupby("filename").agg(
        first_date=("date", "min"),
        last_date=("date", "max")
    ).reset_index()
    grouped_time["코딩 시간"] = grouped_time.apply(lambda row: calculate_duration(row["first_date"], row["last_date"]),
                                               axis=1)

    latest_info = df.sort_values("date").groupby("filename").last().reset_index()

    summary = df.groupby("filename").agg(
        user=("user", "first"),
        date=("date", "max"),
        total_changes_mean=("total_changes", "mean"),
        additions_mean=("additions", "mean"),
        deletions_mean=("deletions", "mean"),
        commit_count=("filename", "count")
    ).reset_index()

    summary = summary.merge(latest_info[["filename", "status", "url"]], on="filename", how="left")
    summary = summary.merge(grouped_time[["filename", "코딩 시간"]], on="filename", how="left")

    summary["loc"] = summary["filename"].apply(lambda f: fetch_loc(repo_owner, repo_name, branch, f, headers))
    summary = summary[summary["loc"].notnull()]
    summary["loc"] = summary["loc"].astype(int)

    summary["code_similarity"] = summary["filename"].apply(
        lambda f: fetch_similarity(
            repo_owner, repo_name, branch, f, headers,
            local_base_dir=week_label,  # ✅ 로컬은 week01 폴더 기준
            directory_prefix=github_directory  # ✅ GitHub는 루트라 prefix 제거 없음("")
        )
    )
    summary["date"] = pd.to_datetime(summary["date"]).dt.strftime("%Y-%m-%d %H:%M")
    summary["result"] = summary["commit_count"].apply(calculate_result)

    summary["파일명 (총 커밋 수)"] = summary.apply(
        lambda row: f'<a href="{row["url"]}" target="_blank">{row["filename"]} ({row["commit_count"]})</a>', axis=1)

    summary = summary.round({
        "total_changes_mean": 2,
        "additions_mean": 2,
        "deletions_mean": 2,
        "code_similarity": 2
    })

    summary["평균 수정 라인 수 (+/-)"] = summary.apply(
        lambda row: f'{row["total_changes_mean"]} ({row["additions_mean"]}/{row["deletions_mean"]})', axis=1
    )

    summary.drop(columns=["filename", "url", "commit_count", "total_changes_mean", "additions_mean", "deletions_mean"],
                 inplace=True)

    # 실제 이름이 있으면 'user' 컬럼 앞에 '이름' 컬럼 추가
    if user_actual_name:
        summary.insert(0, "이름", user_actual_name)

    summary.rename(columns={
        "date": "최근 커밋일시",
        "status": "상태",
        "code_similarity": "코드 유사도",
        "result": "평가"
    }, inplace=True)

    # '이름' 컬럼이 있는 경우에만 순서 조정
    if "이름" in summary.columns:
        summary = summary[[
            "이름", "user", "파일명 (총 커밋 수)", "최근 커밋일시", "상태",
            "평균 수정 라인 수 (+/-)", "코드 유사도", "코딩 시간", "평가"
        ]]
    else:
        summary = summary[[
            "user", "파일명 (총 커밋 수)", "최근 커밋일시", "상태",
            "평균 수정 라인 수 (+/-)", "코드 유사도", "코딩 시간", "평가"
        ]]

    return summary


def _fetch_commits(base_url, headers, params, directory, start_filter, end_filter, username):
    """
    내부에서 재사용되는 커밋 데이터 추출 함수
    """
    raw_data = []
    page = 1

    # name_filter를 설정하는 조건 추가
    name_filter = params.get("author") is None

    while True:
        params["page"] = page
        res = requests.get(base_url, headers=headers, params=params)

        if res.status_code != 200:
            print(f"❌ 커밋 조회 실패 (status code: {res.status_code})")
            return []

        commits = res.json()
        if not commits:
            break

        for commit in commits:
            # name_filter가 true이면 커밋 author 이름을 확인
            if name_filter:
                commit_author_name = commit.get("commit", {}).get("author", {}).get("name", "")
                if commit_author_name != username:
                    continue

            sha = commit["sha"]
            detail_url = f"{base_url}/{sha}"
            detail_res = requests.get(detail_url, headers=headers)
            if detail_res.status_code != 200:
                continue

            detail = detail_res.json()
            date_raw = detail["commit"]["author"]["date"]
            utc_date = datetime.strptime(date_raw, "%Y-%m-%dT%H:%M:%SZ")
            date = utc_date + timedelta(hours=9)

            if not (start_filter <= date <= end_filter):
                continue

            html_url = detail.get("html_url")

            for f in detail.get("files", []):
                filepath = f["filename"]
                status = f.get("status", "")

                # Python 파일만 분석하도록 조건 추가
                if filepath.startswith(directory) and filepath.endswith(".py") and status != "removed":
                    raw_data.append({
                        "user": username,
                        "date": date,
                        "filename": filepath,
                        "total_changes": f.get("changes", 0),
                        "additions": f.get("additions", 0),
                        "deletions": f.get("deletions", 0),
                        "status": status,
                        "url": html_url
                    })

            time.sleep(0.2)
        page += 1
    return raw_data