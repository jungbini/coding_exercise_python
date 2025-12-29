import pandas as pd
from git_analyzer import analyze_commits, RepoNotFoundError
from html_parser import save_dataframe_as_html


def analyze_multiple_users(account_file, branch="main"):
    """
    users_account.txt 파일에서 정보를 읽어와 여러 사용자의 Git 커밋을 분석하고,
    사용자별 및 전체 HTML 요약 보고서를 생성합니다.
    """
    with open(account_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    all_results = []

    for line in lines:
        if not line.strip():
            continue
        try:
            parts = line.strip().split(",")
            github_url, token, username = parts[0], parts[1], parts[2]
            actual_name = parts[3] if len(parts) > 3 else username  # 실제 이름을 가져옴

            print(f"🔍 분석 중: {actual_name} ({github_url})")

            # 실제 이름을 analyze_commits 함수로 전달
            df = analyze_commits(github_url, token, username, directory="", exclude_first_commit=True,
                                 user_actual_name=actual_name)

            if not df.empty:
                all_results.append(df)
            else:
                print(f"⚠️  {actual_name} 에 대한 커밋 데이터 없음.")
        except RepoNotFoundError as e:
            print(f"❌ 오류 발생: {e}")
        except Exception as e:
            print(f"❌ 오류 발생 (줄 내용: {line.strip()}): {e}")

    if all_results:
        combined_df = pd.concat(all_results, ignore_index=True)
        combined_df.to_csv("all_users_summary.csv", index=False)
        print("✅ 모든 사용자의 분석 데이터가 all_users_summary.csv에 저장되었습니다.")

        # 전체 사용자를 합한 종합 HTML 파일 생성
        save_dataframe_as_html(combined_df, output_path="commit_summary.html", title="전체 파일별 커밋 통계")
        print("✅ 전체 사용자의 종합 HTML 보고서가 commit_summary.html로 생성되었습니다.")

        # 사용자별로 HTML 파일 생성
        grouped_by_name = combined_df.groupby('이름')
        for name, group_df in grouped_by_name:
            output_filename = f"commit_summary({name}).html"
            save_dataframe_as_html(group_df, output_path=output_filename, title=f"{name} 파일별 커밋 통계")
            print(f"✅ {name}의 HTML 보고서가 {output_filename}으로 생성되었습니다.")
    else:
        print("❗ 분석할 커밋 데이터가 없습니다.")


if __name__ == "__main__":
    users_account_file = "users_account.txt"
    analyze_multiple_users(users_account_file)
