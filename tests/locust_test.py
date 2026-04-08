import random
import string

from locust import HttpUser, TaskSet, between, task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_url() -> str:
    slug = "".join(random.choices(string.ascii_lowercase, k=8))
    return f"https://{slug}.example.com"


def _random_alias() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=7))


# ---------------------------------------------------------------------------
# Task sets
# ---------------------------------------------------------------------------

class AnonymousTasks(TaskSet):

    short_codes: list[str] = []

    def on_start(self):
        for _ in range(3):
            alias = _random_alias()
            resp = self.client.post(
                "/links/shorten",
                json={"url": _random_url(), "custom_alias": alias},
                name="/links/shorten [seed]",
            )
            if resp.status_code == 200 and resp.json().get("success"):
                self.short_codes.append(alias)

    @task(5)
    def shorten_link(self):
        self.client.post(
            "/links/shorten",
            json={"url": _random_url()},
            name="/links/shorten",
        )

    @task(10)
    def redirect(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        self.client.get(f"/links/{code}", allow_redirects=False, name="/links/{short_code}")

    @task(4)
    def get_stats(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        self.client.get(f"/links/{code}/stats", name="/links/{short_code}/stats")

    @task(3)
    def search(self):
        self.client.get(
            "/links/search",
            params={"original_url": _random_url()},
            name="/links/search",
        )


class AuthenticatedTasks(TaskSet):

    token: str = ""
    short_codes: list[str] = []

    def on_start(self):
        email = f"{_random_alias()}@loadtest.example.com"
        password = "loadtest_pass1"
        self.client.post("/auth/register", json={"email": email, "password": password})
        resp = self.client.post(
            "/auth/jwt/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(5)
    def shorten_authenticated(self):
        resp = self.client.post(
            "/links/shorten",
            json={"url": _random_url()},
            headers=self._auth(),
            name="/links/shorten [auth]",
        )
        if resp.status_code == 200 and resp.json().get("success"):
            self.short_codes.append(resp.json()["short_code"])

    @task(3)
    def update_link(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        self.client.put(
            f"/links/{code}",
            params={"new_url": _random_url()},
            headers=self._auth(),
            name="/links/{short_code} [PUT]",
        )

    @task(2)
    def delete_link(self):
        if not self.short_codes:
            return
        code = self.short_codes.pop(random.randrange(len(self.short_codes)))
        self.client.delete(
            f"/links/{code}",
            headers=self._auth(),
            name="/links/{short_code} [DELETE]",
        )

    @task(1)
    def get_history(self):
        self.client.post(
            "/links/history",
            json={"page": 1, "limit": 20},
            headers=self._auth(),
            name="/links/history",
        )


# ---------------------------------------------------------------------------
# User classes
# ---------------------------------------------------------------------------

class AnonymousUser(HttpUser):

    weight = 4
    wait_time = between(0.5, 2)
    tasks = [AnonymousTasks]


class RegisteredUser(HttpUser):

    weight = 1
    wait_time = between(1, 3)
    tasks = [AuthenticatedTasks]
