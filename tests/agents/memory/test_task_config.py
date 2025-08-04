"""Tests for TaskConfig database operations with real DB engine."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

import pytest
from sqlmodel import select

from agents.memory import MemoryManager
from common.models import Parameter, TaskConfig, TaskDefinition
from common.models.enums import ParameterType
from db.engine import DatabaseEngine


@pytest.fixture
async def db_engine(tmp_path: Path) -> AsyncGenerator[DatabaseEngine, None]:
    """Create a test database engine."""
    db_path = tmp_path / "test_task_config.db"
    engine = DatabaseEngine(db_path)
    await engine.initialize()
    yield engine
    await engine.close()


@pytest.fixture
async def memory_manager(db_engine: DatabaseEngine) -> MemoryManager:
    """Create a memory manager with test database."""
    manager = MemoryManager(db_engine=db_engine)
    await manager.initialize()
    return manager


@pytest.fixture
def sample_task_definition() -> TaskDefinition:
    """Create a sample task definition."""
    return TaskDefinition(
        name="File Processor",
        description="Process files and generate reports",
        instructions="Read file at {file_path}, analyze with {analysis_type}, and generate report",
        input_schema=[
            Parameter(
                name="file_path",
                description="Path to input file",
                type=ParameterType.STRING,
                required=True,
            ),
            Parameter(
                name="analysis_type",
                description="Type of analysis to perform",
                type=ParameterType.STRING,
                required=True,
            ),
            Parameter(
                name="options",
                description="Analysis options",
                type=ParameterType.DICT,
                required=False,
                default={"verbose": False, "format": "json"},
            ),
        ],
        output_schema=[
            Parameter(
                name="report",
                description="Generated report",
                type=ParameterType.DICT,
                required=True,
            ),
            Parameter(
                name="summary",
                description="Brief summary",
                type=ParameterType.STRING,
                required=True,
            ),
        ],
        task_type="analysis",
    )


class TestTaskConfigDatabase:
    """Test TaskConfig database operations."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_task(
        self, memory_manager: MemoryManager, sample_task_definition: TaskDefinition
    ) -> None:
        """Test creating and retrieving a task through memory manager."""
        # Create task config
        task_config = TaskConfig(
            id=str(uuid.uuid4()),
            name=sample_task_definition.name,
            definition=sample_task_definition,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Store via memory manager
        task_id = await memory_manager.create_task(task_config)
        assert task_id == task_config.id

        # Retrieve via memory manager
        retrieved = await memory_manager.get_task(task_id)
        assert retrieved is not None
        assert retrieved.id == task_id
        assert retrieved.name == "File Processor"

        # Verify definition is properly deserialized
        assert isinstance(retrieved.definition, TaskDefinition)
        assert retrieved.definition.name == "File Processor"
        assert len(retrieved.definition.input_schema) == 3
        assert retrieved.definition.input_schema[0].name == "file_path"
        assert retrieved.definition.input_schema[2].default == {"verbose": False, "format": "json"}

    @pytest.mark.asyncio
    async def test_list_tasks(self, memory_manager: MemoryManager) -> None:
        """Test listing multiple tasks."""
        # Create multiple tasks
        task_defs = [
            TaskDefinition(
                name=f"Task {i}",
                description=f"Description {i}",
                instructions=f"Do task {i}",
                input_schema=[
                    Parameter(
                        name="param",
                        description="A parameter",
                        type=ParameterType.STRING,
                        required=True,
                    )
                ],
                output_schema=[],
                task_type=f"type{i}",
            )
            for i in range(5)
        ]

        # Store all tasks
        task_ids = []
        for i, task_def in enumerate(task_defs):
            task_config = TaskConfig(
                id=f"task-{i}",
                name=task_def.name,
                definition=task_def,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            task_id = await memory_manager.create_task(task_config)
            task_ids.append(task_id)

        # List all tasks
        all_tasks = await memory_manager.list_tasks(limit=10)
        assert len(all_tasks) == 5

        # Verify all definitions are TaskDefinition instances
        for task in all_tasks:
            assert isinstance(task.definition, TaskDefinition)
            assert task.definition.name.startswith("Task ")

        # Test with limit
        limited_tasks = await memory_manager.list_tasks(limit=3)
        assert len(limited_tasks) == 3

    @pytest.mark.asyncio
    async def test_update_task_definition(
        self, memory_manager: MemoryManager, sample_task_definition: TaskDefinition
    ) -> None:
        """Test updating a task's definition."""
        # Create initial task
        task_config = TaskConfig(
            id="update-test",
            name="Original Name",
            definition=sample_task_definition,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await memory_manager.create_task(task_config)

        # Retrieve and update
        retrieved = await memory_manager.get_task("update-test")
        assert retrieved is not None

        # Modify the definition
        new_definition = TaskDefinition(
            name="Updated Task",
            description="Updated description",
            instructions="New instructions with {new_param}",
            input_schema=[
                Parameter(
                    name="new_param",
                    description="New parameter",
                    type=ParameterType.STRING,
                    required=True,
                )
            ],
            output_schema=[],
            task_type="updated",
        )

        retrieved.definition = new_definition
        retrieved.name = "Updated Name"
        retrieved.updated_at = datetime.utcnow()

        # Update via backend
        success = await memory_manager._storage.update_task(retrieved)
        assert success is True

        # Verify update
        updated = await memory_manager.get_task("update-test")
        assert updated is not None
        assert updated.name == "Updated Name"
        assert isinstance(updated.definition, TaskDefinition)
        assert updated.definition.name == "Updated Task"
        assert len(updated.definition.input_schema) == 1
        assert updated.definition.input_schema[0].name == "new_param"

    @pytest.mark.asyncio
    async def test_delete_task(
        self, memory_manager: MemoryManager, sample_task_definition: TaskDefinition
    ) -> None:
        """Test deleting a task."""
        # Create task
        task_config = TaskConfig(
            id="delete-test",
            name="To Delete",
            definition=sample_task_definition,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await memory_manager.create_task(task_config)

        # Verify it exists
        exists = await memory_manager.get_task("delete-test")
        assert exists is not None

        # Delete it
        success = await memory_manager._storage.delete_task("delete-test")
        assert success is True

        # Verify it's gone
        deleted = await memory_manager.get_task("delete-test")
        assert deleted is None

    @pytest.mark.asyncio
    async def test_complex_parameter_types(self, memory_manager: MemoryManager) -> None:
        """Test task with complex parameter types and defaults."""
        complex_def = TaskDefinition(
            name="Complex Task",
            description="Task with complex parameters",
            instructions="Process with complex types",
            input_schema=[
                Parameter(
                    name="config",
                    description="Configuration object",
                    type=ParameterType.DICT,
                    required=True,
                ),
                Parameter(
                    name="items",
                    description="List of items to process",
                    type=ParameterType.LIST,
                    required=False,
                    default=["default1", "default2"],
                ),
                Parameter(
                    name="nested_config",
                    description="Nested configuration",
                    type=ParameterType.DICT,
                    required=False,
                    default={
                        "level1": {"level2": {"setting": "value", "number": 42}},
                        "array": [1, 2, 3],
                    },
                ),
            ],
            output_schema=[
                Parameter(
                    name="results",
                    description="Processing results",
                    type=ParameterType.LIST,
                    required=True,
                )
            ],
        )

        task_config = TaskConfig(
            id="complex-task",
            name="Complex Task",
            definition=complex_def,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Store and retrieve
        await memory_manager.create_task(task_config)
        retrieved = await memory_manager.get_task("complex-task")

        # Verify complex defaults are preserved
        assert retrieved is not None
        items_param = next(p for p in retrieved.definition.input_schema if p.name == "items")
        assert items_param.default == ["default1", "default2"]

        nested_param = next(
            p for p in retrieved.definition.input_schema if p.name == "nested_config"
        )
        assert nested_param.default["level1"]["level2"]["number"] == 42  # type: ignore[index]
        assert nested_param.default["array"] == [1, 2, 3]  # type: ignore[index]

    @pytest.mark.asyncio
    async def test_concurrent_task_operations(self, memory_manager: MemoryManager) -> None:
        """Test concurrent task operations."""
        import asyncio

        # Create multiple tasks concurrently
        async def create_task(i: int) -> str:
            task_def = TaskDefinition(
                name=f"Concurrent Task {i}",
                description=f"Task {i}",
                instructions=f"Execute task {i}",
                input_schema=[],
                output_schema=[],
            )
            task_config = TaskConfig(
                id=f"concurrent-{i}",
                name=f"Concurrent {i}",
                definition=task_def,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            return await memory_manager.create_task(task_config)

        # Create 10 tasks concurrently
        tasks = [create_task(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Verify all were created
        assert len(results) == 10
        assert all(r == f"concurrent-{i}" for i, r in enumerate(results))

        # Retrieve all concurrently
        async def get_task(task_id: str) -> Optional[TaskConfig]:
            return await memory_manager.get_task(task_id)

        get_tasks = [get_task(f"concurrent-{i}") for i in range(10)]
        retrieved = await asyncio.gather(*get_tasks)

        # Verify all retrieved correctly
        assert len(retrieved) == 10
        assert all(t is not None for t in retrieved)
        assert all(isinstance(t.definition, TaskDefinition) for t in retrieved if t)

    @pytest.mark.asyncio
    async def test_raw_sql_query(self, db_engine: DatabaseEngine) -> None:
        """Test that we can query tasks with raw SQL and still get proper deserialization."""
        # Create a task directly with the engine
        session_factory = db_engine.get_session_factory()

        task_def = TaskDefinition(
            name="SQL Test Task",
            description="Test raw SQL",
            instructions="Test instructions",
            input_schema=[],
            output_schema=[],
        )

        task_config = TaskConfig(
            id="sql-test",
            name="SQL Test",
            definition=task_def,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        async with session_factory() as session:
            session.add(task_config)
            await session.commit()

        # Query with raw SQL through SQLModel
        async with session_factory() as session:
            result = await session.execute(select(TaskConfig).where(TaskConfig.id == "sql-test"))
            retrieved = result.scalar_one_or_none()

            # Verify PydanticJSON properly deserializes
            assert retrieved is not None
            assert isinstance(retrieved.definition, TaskDefinition)
            assert retrieved.definition.name == "SQL Test Task"
