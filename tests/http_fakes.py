import io


class ArchiveResponse(io.BytesIO):
    def __init__(self, content: bytes, *, status: int = 200):
        super().__init__(content)
        self.status = status
