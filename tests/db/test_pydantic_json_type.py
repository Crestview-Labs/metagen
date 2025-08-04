"""Tests for PydanticJSON custom SQLAlchemy type."""

from datetime import datetime
from typing import Any, Optional

import pytest
from pydantic import BaseModel
from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlmodel import Field, SQLModel, select

from common.models.enums import ParameterType
from common.models.task import Parameter, TaskDefinition
from common.models.types import PydanticJSON


# Test models for comprehensive testing
class TestNestedModel(BaseModel):
    """Nested model for testing."""

    name: str
    value: int
    optional: Optional[str] = None


class TestComplexModel(BaseModel):
    """Complex model with various field types."""

    id: int
    title: str
    nested: TestNestedModel
    items: list[str]
    metadata: dict[str, int]
    is_active: bool = True
    created_at: Optional[datetime] = None


Base: Any = declarative_base()


class TestTable(Base):  # type: ignore[valid-type,misc]
    """Test table with PydanticJSON column."""

    __tablename__ = "test_pydantic_json"

    id = Column(Integer, primary_key=True)
    data: Any = Column(PydanticJSON(TestComplexModel))


class TestTaskConfigTable(SQLModel, table=True):
    """Test version of TaskConfig for isolated testing."""

    __tablename__ = "test_task_configs"

    id: str = Field(primary_key=True)
    name: str
    definition: TaskDefinition = Field(sa_column=Column(PydanticJSON(TaskDefinition)))
    created_at: datetime = Field(default_factory=datetime.utcnow)


@pytest.fixture
def test_engine() -> Any:
    """Create a test SQLite engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def test_session(test_engine: Any) -> Any:
    """Create a test session."""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
async def async_test_engine() -> Any:
    """Create an async test SQLite engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_test_session(async_test_engine: Any) -> Any:
    """Create an async test session."""
    async_session_maker = async_sessionmaker(
        async_test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_maker() as session:
        yield session


class TestPydanticJSONType:
    """Tests for PydanticJSON custom type."""

    def test_serialize_deserialize_basic(self, test_session: Any) -> None:
        """Test basic serialization and deserialization."""
        # Create test data
        nested = TestNestedModel(name="test", value=42, optional="optional_value")
        model = TestComplexModel(
            id=1,
            title="Test Model",
            nested=nested,
            items=["item1", "item2", "item3"],
            metadata={"key1": 10, "key2": 20},
            is_active=True,
            created_at=datetime.utcnow(),
        )

        # Store in database
        row = TestTable(id=1, data=model)
        test_session.add(row)
        test_session.commit()

        # Retrieve from database
        retrieved = test_session.query(TestTable).filter_by(id=1).first()

        # Verify it's deserialized correctly
        assert isinstance(retrieved.data, TestComplexModel)
        assert retrieved.data.id == 1
        assert retrieved.data.title == "Test Model"
        assert retrieved.data.nested.name == "test"
        assert retrieved.data.nested.value == 42
        assert retrieved.data.items == ["item1", "item2", "item3"]
        assert retrieved.data.metadata == {"key1": 10, "key2": 20}
        assert retrieved.data.is_active is True

    def test_null_handling(self, test_session: Any) -> None:
        """Test handling of null values."""
        # Store null
        row = TestTable(id=2, data=None)
        test_session.add(row)
        test_session.commit()

        # Retrieve and verify
        retrieved = test_session.query(TestTable).filter_by(id=2).first()
        assert retrieved.data is None

    def test_update_existing(self, test_session: Any) -> None:
        """Test updating existing records."""
        # Create initial record
        model1 = TestComplexModel(
            id=3,
            title="Original",
            nested=TestNestedModel(name="original", value=1),
            items=["a"],
            metadata={"x": 1},
        )
        row = TestTable(id=3, data=model1)
        test_session.add(row)
        test_session.commit()

        # Update the record
        row = test_session.query(TestTable).filter_by(id=3).first()
        model2 = TestComplexModel(
            id=3,
            title="Updated",
            nested=TestNestedModel(name="updated", value=2),
            items=["b", "c"],
            metadata={"y": 2},
        )
        row.data = model2
        test_session.commit()

        # Verify update
        retrieved = test_session.query(TestTable).filter_by(id=3).first()
        assert retrieved.data.title == "Updated"
        assert retrieved.data.nested.name == "updated"
        assert retrieved.data.items == ["b", "c"]

    def test_invalid_type_error(self) -> None:
        """Test that invalid types raise appropriate errors."""
        pydantic_type = PydanticJSON(TestComplexModel)

        # Test process_bind_param with invalid type
        with pytest.raises(ValueError, match="Expected TestComplexModel or dict"):
            pydantic_type.process_bind_param("invalid", None)

        # Test process_result_value with invalid type
        with pytest.raises(ValueError, match="Expected dict from database"):
            pydantic_type.process_result_value("invalid", None)

    @pytest.mark.asyncio
    async def test_async_operations(self, async_test_session: Any) -> None:
        """Test PydanticJSON with async SQLAlchemy."""
        # Create test data
        model = TestComplexModel(
            id=4,
            title="Async Test",
            nested=TestNestedModel(name="async", value=99),
            items=["async1", "async2"],
            metadata={"async": 1},
        )

        # Store asynchronously
        row = TestTable(id=4, data=model)
        async_test_session.add(row)
        await async_test_session.commit()

        # Retrieve asynchronously
        result = await async_test_session.execute(select(TestTable).where(TestTable.id == 4))
        retrieved = result.scalar_one()

        # Verify
        assert isinstance(retrieved.data, TestComplexModel)
        assert retrieved.data.title == "Async Test"
        assert retrieved.data.nested.value == 99


class TestTaskDefinitionSerialization:
    """Tests specifically for TaskDefinition serialization."""

    def test_task_definition_basic(self, test_session: Any) -> None:
        """Test TaskDefinition serialization/deserialization."""
        # Create a task definition
        task_def = TaskDefinition(
            name="Test Task",
            description="A test task",
            instructions="Do something with {input1} and {input2}",
            input_schema=[
                Parameter(
                    name="input1",
                    description="First input",
                    type=ParameterType.STRING,
                    required=True,
                ),
                Parameter(
                    name="input2",
                    description="Second input",
                    type=ParameterType.INTEGER,
                    required=False,
                    default=10,
                ),
            ],
            output_schema=[
                Parameter(
                    name="result", description="The result", type=ParameterType.DICT, required=True
                )
            ],
            task_type="test",
        )

        # Store in database
        task_config = TestTaskConfigTable(id="test-123", name="Test Task", definition=task_def)
        test_session.add(task_config)
        test_session.commit()

        # Retrieve
        retrieved = test_session.query(TestTaskConfigTable).filter_by(id="test-123").first()

        # Verify TaskDefinition is properly deserialized
        assert isinstance(retrieved.definition, TaskDefinition)
        assert retrieved.definition.name == "Test Task"
        assert retrieved.definition.description == "A test task"
        assert len(retrieved.definition.input_schema) == 2
        assert retrieved.definition.input_schema[0].name == "input1"
        assert retrieved.definition.input_schema[0].type == ParameterType.STRING
        assert retrieved.definition.input_schema[1].default == 10
        assert len(retrieved.definition.output_schema) == 1
        assert retrieved.definition.task_type == "test"

    def test_task_definition_all_parameter_types(self, test_session: Any) -> None:
        """Test TaskDefinition with all parameter types."""
        # Create task with all parameter types
        task_def = TaskDefinition(
            name="All Types Task",
            description="Task with all parameter types",
            instructions="Process all types",
            input_schema=[
                Parameter(
                    name="string_param",
                    description="String",
                    type=ParameterType.STRING,
                    required=True,
                ),
                Parameter(
                    name="int_param",
                    description="Integer",
                    type=ParameterType.INTEGER,
                    required=True,
                ),
                Parameter(
                    name="float_param", description="Float", type=ParameterType.FLOAT, required=True
                ),
                Parameter(
                    name="bool_param",
                    description="Boolean",
                    type=ParameterType.BOOLEAN,
                    required=True,
                ),
                Parameter(
                    name="list_param",
                    description="List",
                    type=ParameterType.LIST,
                    required=False,
                    default=[],
                ),
                Parameter(
                    name="dict_param",
                    description="Dict",
                    type=ParameterType.DICT,
                    required=False,
                    default={},
                ),
            ],
            output_schema=[],
        )

        # Store and retrieve
        task_config = TestTaskConfigTable(id="all-types", name="All Types", definition=task_def)
        test_session.add(task_config)
        test_session.commit()

        retrieved = test_session.query(TestTaskConfigTable).filter_by(id="all-types").first()

        # Verify all parameter types
        assert len(retrieved.definition.input_schema) == 6
        param_types = {p.name: p.type for p in retrieved.definition.input_schema}
        assert param_types["string_param"] == ParameterType.STRING
        assert param_types["int_param"] == ParameterType.INTEGER
        assert param_types["float_param"] == ParameterType.FLOAT
        assert param_types["bool_param"] == ParameterType.BOOLEAN
        assert param_types["list_param"] == ParameterType.LIST
        assert param_types["dict_param"] == ParameterType.DICT

    @pytest.mark.asyncio
    async def test_task_config_integration(self, async_test_session: Any) -> None:
        """Test full TaskConfig integration with async SQLAlchemy."""
        # Create a complete TaskConfig
        task_def = TaskDefinition(
            name="Integration Test Task",
            description="Full integration test",
            instructions="Execute {command} on {target}",
            input_schema=[
                Parameter(
                    name="command",
                    description="Command to execute",
                    type=ParameterType.STRING,
                    required=True,
                ),
                Parameter(
                    name="target",
                    description="Target system",
                    type=ParameterType.STRING,
                    required=True,
                ),
                Parameter(
                    name="options",
                    description="Execution options",
                    type=ParameterType.DICT,
                    required=False,
                    default={"timeout": 30, "retries": 3},
                ),
            ],
            output_schema=[
                Parameter(
                    name="status",
                    description="Execution status",
                    type=ParameterType.STRING,
                    required=True,
                ),
                Parameter(
                    name="output",
                    description="Command output",
                    type=ParameterType.STRING,
                    required=False,
                ),
            ],
        )

        task_config = TestTaskConfigTable(
            id="integration-test",
            name="Integration Task",
            definition=task_def,
            created_at=datetime.utcnow(),
        )

        # Store
        async_test_session.add(task_config)
        await async_test_session.commit()

        # Retrieve using SQLModel select
        result = await async_test_session.execute(
            select(TestTaskConfigTable).where(TestTaskConfigTable.id == "integration-test")
        )
        retrieved = result.scalar_one()

        # Comprehensive verification
        assert isinstance(retrieved.definition, TaskDefinition)
        assert retrieved.definition.name == "Integration Test Task"
        assert "Execute {command}" in retrieved.definition.instructions

        # Verify parameter defaults are preserved
        options_param = next(p for p in retrieved.definition.input_schema if p.name == "options")
        assert options_param.default == {"timeout": 30, "retries": 3}

        # Verify we can access nested properties
        assert retrieved.definition.input_schema[0].description == "Command to execute"
        assert retrieved.definition.output_schema[0].type == ParameterType.STRING

    def test_edge_cases(self, test_session: Any) -> None:
        """Test edge cases in serialization."""
        # Empty schemas
        task_def1 = TaskDefinition(
            name="Empty Task",
            description="No parameters",
            instructions="Do nothing",
            input_schema=[],
            output_schema=[],
        )

        task1 = TestTaskConfigTable(id="empty", name="Empty", definition=task_def1)
        test_session.add(task1)

        # Very long instructions and descriptions
        long_text = "x" * 1000
        task_def2 = TaskDefinition(
            name="Long Task",
            description=long_text,
            instructions=long_text,
            input_schema=[
                Parameter(
                    name="param", description=long_text, type=ParameterType.STRING, required=True
                )
            ],
            output_schema=[],
        )

        task2 = TestTaskConfigTable(id="long", name="Long", definition=task_def2)
        test_session.add(task2)

        test_session.commit()

        # Verify both are stored and retrieved correctly
        empty_retrieved = test_session.query(TestTaskConfigTable).filter_by(id="empty").first()
        assert len(empty_retrieved.definition.input_schema) == 0
        assert len(empty_retrieved.definition.output_schema) == 0

        long_retrieved = test_session.query(TestTaskConfigTable).filter_by(id="long").first()
        assert len(long_retrieved.definition.description) == 1000
        assert len(long_retrieved.definition.instructions) == 1000
