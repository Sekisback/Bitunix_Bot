import pytest
from manager.grid_manager import GridManager, GridLevel

class MockExchange:
    """Mock für die Bitunix-API."""
    def __init__(self):
        self.orders = {}
        self.counter = 0

    def place_limit_order(self, symbol, side, price, size, mode):
        self.counter += 1
        order_id = f"MOCK-{self.counter}"
        self.orders[order_id] = {"symbol": symbol, "side": side, "price": price, "size": size, "filled": False}
        return order_id

    def check_filled_orders(self, order_ids):
        # Simuliere: jede zweite Order gilt als "gefüllt"
        filled = []
        for i, oid in enumerate(order_ids):
            if i % 2 == 0:
                self.orders[oid]["filled"] = True
                filled.append(oid)
        return filled


@pytest.fixture
def mock_config():
    return {
        "symbol": "ONDOUSDT",
        "order_size": 10,
        "grid_step_pct": 1.0,
        "num_grids": 3,
        "mode": "isolated"
    }


@pytest.fixture
def mock_exchange():
    return MockExchange()


def test_initialize_grid(mock_config, mock_exchange):
    gm = GridManager(mock_config, mock_exchange)
    levels = gm.initialize_grid(1.0)
    assert len(levels) == 6
    assert levels[0].price < levels[-1].price


def test_place_orders(mock_config, mock_exchange):
    gm = GridManager(mock_config, mock_exchange)
    gm.initialize_grid(1.0)
    gm.place_orders()
    assert len(gm.active_orders) == 6
    assert all(isinstance(level.order_id, str) for level in gm.grid_levels)


def test_update_places_opposite_orders(mock_config, mock_exchange):
    gm = GridManager(mock_config, mock_exchange)
    gm.initialize_grid(1.0)
    gm.place_orders()
    gm.update(1.05)
    assert len(gm.active_orders) > 0


if __name__ == "__main__":
    import pytest
    pytest.main(["-v", __file__])
