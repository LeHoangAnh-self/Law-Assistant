from __future__ import annotations

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from qna_crawler.config import Settings
from qna_crawler.models import GovernmentQnaCitation, GovernmentQnaItem


def create_db_engine(settings: Settings) -> Engine:
    connect_args = {}
    if settings.database_url.startswith("mysql+mysqlconnector://"):
        connect_args["use_pure"] = True
    return create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_engine_from_url(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("mysql+mysqlconnector://"):
        connect_args["use_pure"] = True
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    GovernmentQnaItem.__table__.create(engine, checkfirst=True)
    GovernmentQnaCitation.__table__.create(engine, checkfirst=True)
    _run_mysql_compat_migrations(engine)


def _run_mysql_compat_migrations(engine: Engine) -> None:
    if engine.dialect.name != "mysql":
        return
    with engine.begin() as connection:
        _create_table_if_missing(
            connection,
            "government_qna_items",
            """
            create table government_qna_items (
                id bigint not null auto_increment,
                external_id bigint null,
                source_name varchar(255) not null,
                source_url varchar(1500) not null,
                source_url_hash char(64) not null,
                detail_url varchar(1500),
                original_url varchar(1500),
                title varchar(1500) not null,
                question_text mediumtext,
                answer_text longtext,
                answer_html longtext,
                summary_text mediumtext,
                responding_authority varchar(500),
                category_name varchar(500),
                tags varchar(1000),
                published_date date,
                source_payload_json longtext,
                content_hash varchar(64),
                citation_status varchar(32) not null default 'UNRESOLVED',
                citation_count int not null default 0,
                matched_citation_count int not null default 0,
                missing_citation_count int not null default 0,
                crawled_at datetime default current_timestamp,
                updated_at datetime default current_timestamp on update current_timestamp,
                primary key (id),
                unique key uk_government_qna_source_url_hash (source_url_hash),
                key idx_government_qna_source (source_name),
                key idx_government_qna_published_at (published_date),
                key idx_government_qna_item_citation_status (citation_status)
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "government_qna_citations",
            """
            create table government_qna_citations (
                id bigint not null auto_increment,
                qna_item_id bigint not null,
                citation_hash char(64) not null,
                raw_text varchar(1500) not null,
                document_number varchar(255),
                document_title varchar(1000),
                article_refs varchar(1000),
                matched_document_id bigint,
                matched_document_title varchar(1500),
                matched_document_number varchar(255),
                matched_document_source varchar(2048),
                match_status varchar(32) not null,
                match_reason varchar(500),
                created_at datetime default current_timestamp,
                primary key (id),
                unique key uk_government_qna_citation_hash (qna_item_id, citation_hash),
                key idx_government_qna_citation_document (matched_document_id),
                key idx_government_qna_citation_status (match_status),
                key idx_government_qna_citation_number (document_number),
                constraint fk_government_qna_citations_item
                    foreign key (qna_item_id) references government_qna_items(id) on delete cascade
            )
            """,
        )
        _add_column_if_missing(
            connection,
            "government_qna_citations",
            "matched_document_title",
            "varchar(1500)",
        )
        _add_column_if_missing(
            connection,
            "government_qna_citations",
            "matched_document_number",
            "varchar(255)",
        )
        _add_column_if_missing(
            connection,
            "government_qna_citations",
            "matched_document_source",
            "varchar(2048)",
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
