import time

from PIL import ImageDraw


class TestProvider:
    __test__ = False
    name = "Test fixture (not AI)"

    def status(self):
        return {"ready": True, "name": self.name, "mode": "local", "message": "Test-only provider"}

    def generate(self, person, garment, options):
        time.sleep(0.1)
        result = person.copy()
        ImageDraw.Draw(result).rectangle((40, 80, 100, 120), fill="green")
        return result


class PublicTestProvider(TestProvider):
    """Exercises public-mode UI/API consent, without any external requests."""

    def status(self):
        return {**super().status(), "mode": "public", "supports_preservation": False}
