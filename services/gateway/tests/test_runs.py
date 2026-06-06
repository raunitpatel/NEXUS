"""Unit tests for services/gateway/routers/runs.py.

External dependencies are mocked, so tests run in isolation.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


@pytest.fixture()
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_cancel_run_pending_returns_cancelled_response(
    mock_db_session: AsyncMock,
) -> None:
    """Cancelling a pending run returns a CancelRunResponse with cancelled status."""
    from routers.runs import cancel_run

    run_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    mock_result = MagicMock()
    mock_result.fetchone.return_value = MagicMock(id=run_id)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    response = await cancel_run(
        run_id=run_id,
        current_user={"user_id": user_id},
        db=mock_db_session,
    )

    assert response.run_id == run_id
    assert response.status == "cancelled"
    mock_db_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_run_not_found_raises_404(mock_db_session: AsyncMock) -> None:
    """Cancelling a run that does not exist returns 404."""
    from routers.runs import cancel_run

    run_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    mock_update_result = MagicMock()
    mock_update_result.fetchone.return_value = None

    mock_owner_check = MagicMock()
    mock_owner_check.fetchone.return_value = None

    mock_db_session.execute = AsyncMock(side_effect=[mock_update_result, mock_owner_check])

    with pytest.raises(HTTPException) as exc_info:
        await cancel_run(run_id=run_id, current_user={"user_id": user_id}, db=mock_db_session)

    assert exc_info.value.status_code == 404
    mock_db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_run_terminal_status_raises_409(mock_db_session: AsyncMock) -> None:
    """Cancelling a run already in a terminal state returns 409."""
    from routers.runs import cancel_run

    run_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    mock_update_result = MagicMock()
    mock_update_result.fetchone.return_value = None

    mock_owner_check = MagicMock()
    mock_owner_check.fetchone.return_value = 1

    mock_db_session.execute = AsyncMock(side_effect=[mock_update_result, mock_owner_check])

    with pytest.raises(HTTPException) as exc_info:
        await cancel_run(run_id=run_id, current_user={"user_id": user_id}, db=mock_db_session)

    assert exc_info.value.status_code == 409
    mock_db_session.commit.assert_not_awaited()
