# football-betting-common

仓库内 Python 子包：供 `football-betting-platform`、`football-betting-partner` 等共用。

当前包含：

- **环境变量**：与各子项目一致的根目录 / 子项目 / CWD `.env` 加载顺序。
- **MySQL**：`DATABASE_URL` 占位符校验、PyMySQL 自定义 `creator`（支持密码中的非 ASCII），供 Flask-SQLAlchemy `SQLALCHEMY_ENGINE_OPTIONS` 使用；`sqlite` URL 返回空 option。

安装（在子项目虚拟环境中）：

```bash
pip install -e ../football-betting-common
```

后续可逐步把 **SQLAlchemy 模型** 等迁入本包（需与各服务的 `db.Model` 衔接方式一并设计）。
