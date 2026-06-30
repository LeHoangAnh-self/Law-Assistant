from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from law_crawler.config import Settings
from law_crawler.models import Base


def create_db_engine(settings: Settings) -> Engine:
    connect_args = {}
    if settings.database_url.startswith("mysql+mysqlconnector://"):
        connect_args["use_pure"] = True
    return create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _run_mysql_compat_migrations(engine)


def _run_mysql_compat_migrations(engine: Engine) -> None:
    if engine.dialect.name != "mysql":
        return

    with engine.begin() as connection:
        _create_table_if_missing(
            connection,
            "duplicate_legal_identity_reviews",
            """
            create table duplicate_legal_identity_reviews (
                id bigint not null auto_increment,
                document_id bigint not null,
                duplicate_document_id bigint not null,
                identity_key varchar(64) not null,
                document_number varchar(255),
                issued_date date,
                issuing_authority varchar(500),
                source_url varchar(1500),
                duplicate_source_url varchar(1500),
                status varchar(32) not null default 'OPEN',
                review_reason varchar(255) not null default 'SAME_LEGAL_IDENTITY_DIFFERENT_DOCUMENT_ID',
                created_at datetime default current_timestamp,
                updated_at datetime default current_timestamp on update current_timestamp,
                primary key (id),
                unique key uk_duplicate_legal_identity_pair (document_id, duplicate_document_id),
                key idx_duplicate_legal_identity_status (status),
                key idx_duplicate_legal_identity_key (identity_key)
            )
            """,
        )
        _add_column_if_missing(
            connection,
            "legal_document_clauses",
            "clause_occurrence",
            "int not null default 1",
        )
        _add_column_if_missing(
            connection,
            "legal_document_articles",
            "article_occurrence",
            "int not null default 1",
        )
        _add_index_if_missing(
            connection,
            "legal_document_articles",
            "idx_articles_version_id",
            "key idx_articles_version_id (version_id)",
        )
        _drop_index_if_exists(connection, "legal_document_articles", "uk_version_article_number")
        _add_index_if_missing(
            connection,
            "legal_document_articles",
            "uk_version_article_occurrence",
            "unique key uk_version_article_occurrence (version_id, article_number, article_occurrence)",
        )
        _add_column_if_missing(
            connection,
            "legal_document_points",
            "point_occurrence",
            "int not null default 1",
        )
        connection.execute(text("alter table crawl_jobs modify status varchar(32) not null default 'DISCOVERED'"))
        _add_index_if_missing(
            connection,
            "legal_document_clauses",
            "idx_clauses_article_id",
            "key idx_clauses_article_id (article_id)",
        )
        _add_index_if_missing(
            connection,
            "legal_document_points",
            "idx_points_clause_id",
            "key idx_points_clause_id (clause_id)",
        )
        _drop_index_if_exists(connection, "legal_document_clauses", "uk_article_clause_number")
        _drop_index_if_exists(connection, "legal_document_points", "uk_clause_point_label")
        _add_index_if_missing(
            connection,
            "legal_document_clauses",
            "uk_article_clause_occurrence",
            "unique key uk_article_clause_occurrence (article_id, clause_number, clause_occurrence)",
        )
        _add_index_if_missing(
            connection,
            "legal_document_points",
            "uk_clause_point_occurrence",
            "unique key uk_clause_point_occurrence (clause_id, point_label, point_occurrence)",
        )


def _create_table_if_missing(connection, table_name: str, ddl: str) -> None:
    exists = connection.scalar(
        text(
            """
            select count(*)
            from information_schema.tables
            where table_schema = database()
              and table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    if not exists:
        connection.execute(text(ddl))


def _add_column_if_missing(connection, table_name: str, column_name: str, ddl: str) -> None:
    exists = connection.scalar(
        text(
            """
            select count(*)
            from information_schema.columns
            where table_schema = database()
              and table_name = :table_name
              and column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    if not exists:
        connection.execute(text(f"alter table {table_name} add column {column_name} {ddl}"))


def _drop_index_if_exists(connection, table_name: str, index_name: str) -> None:
    exists = connection.scalar(
        text(
            """
            select count(*)
            from information_schema.statistics
            where table_schema = database()
              and table_name = :table_name
              and index_name = :index_name
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    )
    if exists:
        connection.execute(text(f"alter table {table_name} drop index {index_name}"))


def _add_index_if_missing(connection, table_name: str, index_name: str, ddl: str) -> None:
    exists = connection.scalar(
        text(
            """
            select count(*)
            from information_schema.statistics
            where table_schema = database()
              and table_name = :table_name
              and index_name = :index_name
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    )
    if not exists:
        connection.execute(text(f"alter table {table_name} add {ddl}"))
