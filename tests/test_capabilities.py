"""Tests for capability modules."""

import asyncio
import os
import tempfile
import pytest

from wish_granter.capabilities.base import Capability, CapabilityResult
from wish_granter.capabilities.file_io import FileIOCapability
from wish_granter.capabilities.data_analysis import DataAnalysisCapability
from wish_granter.capabilities.shell import ShellCapability


class TestCapabilityResult:
    def test_success_result(self):
        result = CapabilityResult(success=True, data={"key": "value"}, capability_name="test")
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self):
        result = CapabilityResult(success=False, error="something failed", capability_name="test")
        assert result.success is False
        assert result.error == "something failed"


class TestFileIOCapability:
    @pytest.fixture
    def tmpdir(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    @pytest.fixture
    def file_io(self, tmpdir):
        return FileIOCapability({"sandbox_root": tmpdir})

    @pytest.mark.asyncio
    async def test_write_and_read(self, file_io, tmpdir):
        path = os.path.join(tmpdir, "test.txt")
        write_result = await file_io.execute({"action": "write", "path": path, "content": "Hello World"})
        assert write_result.success
        assert write_result.data["size"] > 0

        read_result = await file_io.execute({"action": "read", "path": path})
        assert read_result.success
        assert read_result.data["content"] == "Hello World"

    @pytest.mark.asyncio
    async def test_write_and_append(self, file_io, tmpdir):
        path = os.path.join(tmpdir, "append.txt")
        await file_io.execute({"action": "write", "path": path, "content": "Line 1\n"})
        append_result = await file_io.execute({"action": "append", "path": path, "content": "Line 2\n"})
        assert append_result.success

        read_result = await file_io.execute({"action": "read", "path": path})
        assert "Line 1" in read_result.data["content"]
        assert "Line 2" in read_result.data["content"]

    @pytest.mark.asyncio
    async def test_mkdir(self, file_io, tmpdir):
        path = os.path.join(tmpdir, "subdir", "deep")
        result = await file_io.execute({"action": "mkdir", "path": path})
        assert result.success
        assert os.path.isdir(path)

    @pytest.mark.asyncio
    async def test_list_dir(self, file_io, tmpdir):
        for name in ["a.txt", "b.txt", "c.py"]:
            await file_io.execute({"action": "write", "path": os.path.join(tmpdir, name), "content": "test"})

        result = await file_io.execute({"action": "list", "path": tmpdir})
        assert result.success
        assert result.data["total"] >= 3

    @pytest.mark.asyncio
    async def test_exists(self, file_io, tmpdir):
        path = os.path.join(tmpdir, "exists.txt")
        result = await file_io.execute({"action": "exists", "path": path})
        assert result.success
        assert result.data["exists"] is False

        await file_io.execute({"action": "write", "path": path, "content": "hello"})
        result = await file_io.execute({"action": "exists", "path": path})
        assert result.data["exists"] is True

    @pytest.mark.asyncio
    async def test_copy(self, file_io, tmpdir):
        src = os.path.join(tmpdir, "src.txt")
        dst = os.path.join(tmpdir, "dst.txt")
        await file_io.execute({"action": "write", "path": src, "content": "copy me"})

        result = await file_io.execute({"action": "copy", "path": src, "destination": dst})
        assert result.success

        read = await file_io.execute({"action": "read", "path": dst})
        assert read.data["content"] == "copy me"

    @pytest.mark.asyncio
    async def test_move(self, file_io, tmpdir):
        src = os.path.join(tmpdir, "src.txt")
        dst = os.path.join(tmpdir, "dst.txt")
        await file_io.execute({"action": "write", "path": src, "content": "move me"})

        result = await file_io.execute({"action": "move", "path": src, "destination": dst})
        assert result.success

        src_check = await file_io.execute({"action": "exists", "path": src})
        assert src_check.data["exists"] is False

    @pytest.mark.asyncio
    async def test_delete(self, file_io, tmpdir):
        path = os.path.join(tmpdir, "del.txt")
        await file_io.execute({"action": "write", "path": path, "content": "delete me"})
        result = await file_io.execute({"action": "delete", "path": path})
        assert result.success
        assert not os.path.exists(path)

    @pytest.mark.asyncio
    async def test_info(self, file_io, tmpdir):
        path = os.path.join(tmpdir, "info.txt")
        await file_io.execute({"action": "write", "path": path, "content": "info test"})
        result = await file_io.execute({"action": "info", "path": path})
        assert result.success
        assert result.data["size"] > 0
        assert result.data["name"] == "info.txt"
        assert result.data["suffix"] == ".txt"

    @pytest.mark.asyncio
    async def test_search_files(self, file_io, tmpdir):
        for name in ["report1.txt", "report2.txt", "data.csv"]:
            await file_io.execute({"action": "write", "path": os.path.join(tmpdir, name), "content": "data"})
        result = await file_io.execute({"action": "search", "path": tmpdir, "query": "report"})
        assert result.success
        assert result.data["total"] == 2

    @pytest.mark.asyncio
    async def test_no_query_error(self, file_io):
        result = await file_io.execute({"action": "read", "path": ""})
        # Should handle gracefully
        assert isinstance(result, CapabilityResult)

    @pytest.mark.asyncio
    async def test_sandbox_restriction(self, tmpdir):
        io = FileIOCapability({"sandbox_root": tmpdir})
        result = await io.execute({"action": "read", "path": "/etc/passwd"})
        assert result.success is False
        assert "sandbox" in (result.error or "").lower() or result.success is False


class TestDataAnalysisCapability:
    @pytest.fixture
    def analyzer(self):
        return DataAnalysisCapability()

    @pytest.mark.asyncio
    async def test_describe_numeric_list(self, analyzer):
        result = await analyzer.execute({"action": "describe", "data": [1, 2, 3, 4, 5]})
        result_dict = result.data
        assert result.success
        assert result_dict["count"] == 5
        assert result_dict["mean"] == 3.0
        assert result_dict["min"] == 1
        assert result_dict["max"] == 5

    @pytest.mark.asyncio
    async def test_describe_dicts(self, analyzer):
        data = [
            {"name": "Alice", "age": 30, "score": 85},
            {"name": "Bob", "age": 25, "score": 92},
            {"name": "Charlie", "age": 35, "score": 78},
        ]
        result = await analyzer.execute({"action": "describe", "data": data})
        assert result.success
        assert "age" in result.data["numeric"]
        assert "name" in result.data["categorical"]

    @pytest.mark.asyncio
    async def test_correlate(self, analyzer):
        data = [
            {"x": 1, "y": 2}, {"x": 2, "y": 4},
            {"x": 3, "y": 6}, {"x": 4, "y": 8},
        ]
        result = await analyzer.execute({"action": "correlate", "data": data, "field_x": "x", "field_y": "y"})
        assert result.success
        assert abs(result.data["correlation"] - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_aggregate(self, analyzer):
        data = [
            {"dept": "sales", "revenue": 100},
            {"dept": "sales", "revenue": 200},
            {"dept": "eng", "revenue": 300},
        ]
        result = await analyzer.execute({"action": "aggregate", "data": data, "field": "revenue", "group_by": "dept", "function": "sum"})
        assert result.success
        assert "sales" in result.data["results"]
        assert result.data["results"]["sales"] == 300.0

    @pytest.mark.asyncio
    async def test_filter(self, analyzer):
        data = [
            {"name": "A", "val": 10},
            {"name": "B", "val": 20},
            {"name": "C", "val": 30},
        ]
        result = await analyzer.execute({"action": "filter", "data": data, "field": "val", "operator": "gt", "value": 15})
        assert result.success
        assert result.data["filtered_count"] == 2

    @pytest.mark.asyncio
    async def test_sort(self, analyzer):
        data = [{"name": "C", "score": 30}, {"name": "A", "score": 10}, {"name": "B", "score": 20}]
        result = await analyzer.execute({"action": "sort", "data": data, "field": "score"})
        assert result.success
        assert result.data["data"][0]["name"] == "A"

    @pytest.mark.asyncio
    async def test_frequency(self, analyzer):
        data = [{"color": "red"}, {"color": "blue"}, {"color": "red"}, {"color": "green"}, {"color": "red"}]
        result = await analyzer.execute({"action": "frequency", "data": data, "field": "color"})
        assert result.success
        assert result.data["frequency"]["red"] == 3

    @pytest.mark.asyncio
    async def test_insights(self, analyzer):
        data = [{"x": 1}, {"x": 2}, {"x": 3}, {"x": 100}]
        result = await analyzer.execute({"action": "insights", "data": data})
        assert result.success
        assert len(result.data["insights"]) > 0

    @pytest.mark.asyncio
    async def test_empty_data(self, analyzer):
        result = await analyzer.execute({"action": "describe", "data": []})
        result2 = await analyzer.execute({"action": "describe"})
        # Should handle gracefully


class TestShellCapability:
    @pytest.fixture
    def shell(self):
        return ShellCapability()

    @pytest.mark.asyncio
    async def test_echo(self, shell):
        result = await shell.execute({"command": "echo hello world"})
        assert result.success
        assert "hello world" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_pwd(self, shell):
        result = await shell.execute({"command": "pwd"})
        assert result.success
        assert "/" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_blocked_command(self, shell):
        result = await shell.execute({"command": "rm -rf /"})
        assert result.success is False
        assert "Blocked" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self, shell):
        result = await shell.execute({"command": "sleep 5", "timeout": 1})
        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_command(self, shell):
        result = await shell.execute({"command": "nonexistent_command_xyz"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_allowed_commands_restriction(self):
        shell = ShellCapability({"allowed_commands": ["echo", "ls"]})
        result = await shell.execute({"command": "echo allowed"})
        assert result.success

        result = await shell.execute({"command": "pwd"})
        assert result.success is False
        assert "not allowed" in result.error