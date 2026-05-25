"""
AtlantisHook — posts cost report as GitHub PR comment.
Called by Atlantis post-apply hook via atlantis.yaml.
"""
import os
import requests


class AtlantisHook:
    def __init__(self):
        self.token   = (os.environ.get("GITHUB_TOKEN", "") or os.environ.get("ATLANTIS_GH_TOKEN", ""))
        self.repo    = (os.environ.get("ATLANTIS_REPO_NAME") or os.environ.get("BASE_REPO_NAME", ""))
        self.pr_num  = (os.environ.get("ATLANTIS_PULL_NUM") or os.environ.get("PULL_NUM", ""))
        self.api_url = os.environ.get(
            "GITHUB_API_URL", "https://api.github.com"
        )

    def post_comment(self, markdown: str) -> bool:
        if not all([self.token, self.repo, self.pr_num]):
            print("[atlantis] Skipping PR comment — env vars not set.")
            print("[atlantis] Need: GITHUB_TOKEN, ATLANTIS_REPO_NAME, ATLANTIS_PULL_NUM")
            return False

        url  = f"{self.api_url}/repos/{self.repo}/issues/{self.pr_num}/comments"
        hdrs = {
            "Authorization": f"token {self.token}",
            "Accept":        "application/vnd.github.v3+json",
        }
        resp = requests.post(
            url, headers=hdrs, json={"body": markdown}, timeout=30
        )
        if resp.ok:
            print(f"[atlantis] Posted cost report to PR #{self.pr_num}")
            return True
        print(f"[atlantis] Failed: {resp.status_code} {resp.text[:200]}")
        return False
