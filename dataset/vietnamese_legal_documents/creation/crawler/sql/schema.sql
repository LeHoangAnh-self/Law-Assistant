create table if not exists legal_documents (
    id bigint not null,
    title varchar(1500) not null,
    document_number varchar(255),
    issued_date date,
    document_type varchar(255),
    effective_date date,
    expired_date date,
    source varchar(1500),
    validity_status varchar(255),
    issuing_authority varchar(500),
    current_version_id bigint null,
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp on update current_timestamp,
    primary key (id),
    index idx_legal_documents_type (document_type),
    index idx_legal_documents_status (validity_status),
    fulltext index ft_legal_documents_title_number (title, document_number)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_versions (
    id bigint not null auto_increment,
    document_id bigint not null,
    version_label varchar(255) not null,
    source_url varchar(1500),
    effective_date date,
    expired_date date,
    validity_status varchar(255),
    superseded_by_version_id bigint null,
    amendment_summary text,
    is_current boolean not null default true,
    crawled_at timestamp not null default current_timestamp,
    source_hash varchar(64),
    primary key (id),
    unique key uk_document_version_label (document_id, version_label),
    index idx_document_versions_current (document_id, is_current),
    constraint fk_versions_document foreign key (document_id) references legal_documents(id) on delete cascade,
    constraint fk_versions_superseded_by foreign key (superseded_by_version_id) references legal_document_versions(id) on delete set null
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

alter table legal_documents
    add constraint fk_legal_documents_current_version
    foreign key (current_version_id) references legal_document_versions(id) on delete set null;

create table if not exists legal_document_contents (
    document_id bigint not null,
    version_id bigint not null,
    content_html mediumtext not null,
    content_text mediumtext,
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp on update current_timestamp,
    primary key (document_id),
    index idx_contents_version (version_id),
    fulltext index ft_legal_document_contents_text (content_text),
    constraint fk_contents_document foreign key (document_id) references legal_documents(id) on delete cascade,
    constraint fk_contents_version foreign key (version_id) references legal_document_versions(id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_articles (
    id bigint not null auto_increment,
    document_id bigint not null,
    version_id bigint not null,
    article_number varchar(64) not null,
    article_occurrence int not null default 1,
    title varchar(1000),
    stable_anchor varchar(255) not null,
    order_index int not null,
    content_text mediumtext not null,
    content_html mediumtext,
    primary key (id),
    unique key uk_version_article_occurrence (version_id, article_number, article_occurrence),
    index idx_articles_version_id (version_id),
    index idx_articles_anchor (stable_anchor),
    fulltext index ft_articles_text (content_text),
    constraint fk_articles_version foreign key (version_id) references legal_document_versions(id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_clauses (
    id bigint not null auto_increment,
    article_id bigint not null,
    clause_number varchar(64) not null,
    clause_occurrence int not null default 1,
    stable_anchor varchar(255) not null,
    order_index int not null,
    content_text mediumtext not null,
    content_html mediumtext,
    primary key (id),
    unique key uk_article_clause_occurrence (article_id, clause_number, clause_occurrence),
    index idx_clauses_article_id (article_id),
    index idx_clauses_anchor (stable_anchor),
    fulltext index ft_clauses_text (content_text),
    constraint fk_clauses_article foreign key (article_id) references legal_document_articles(id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_points (
    id bigint not null auto_increment,
    clause_id bigint not null,
    point_label varchar(32) not null,
    point_occurrence int not null default 1,
    stable_anchor varchar(255) not null,
    order_index int not null,
    content_text mediumtext not null,
    content_html mediumtext,
    primary key (id),
    unique key uk_clause_point_occurrence (clause_id, point_label, point_occurrence),
    index idx_points_clause_id (clause_id),
    index idx_points_anchor (stable_anchor),
    fulltext index ft_points_text (content_text),
    constraint fk_points_clause foreign key (clause_id) references legal_document_clauses(id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_tables (
    id bigint not null auto_increment,
    version_id bigint not null,
    article_id bigint null,
    stable_anchor varchar(255) not null,
    order_index int not null,
    caption varchar(1000),
    html mediumtext not null,
    text mediumtext,
    primary key (id),
    constraint fk_tables_version foreign key (version_id) references legal_document_versions(id) on delete cascade,
    constraint fk_tables_article foreign key (article_id) references legal_document_articles(id) on delete set null
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_forms (
    id bigint not null auto_increment,
    version_id bigint not null,
    stable_anchor varchar(255) not null,
    title varchar(1000),
    source_url varchar(1000),
    html mediumtext,
    text mediumtext,
    primary key (id),
    constraint fk_forms_version foreign key (version_id) references legal_document_versions(id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_annexes (
    id bigint not null auto_increment,
    version_id bigint not null,
    stable_anchor varchar(255) not null,
    title varchar(1000),
    order_index int not null,
    html longtext,
    text longtext,
    primary key (id),
    constraint fk_annexes_version foreign key (version_id) references legal_document_versions(id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_anchors (
    id bigint not null auto_increment,
    version_id bigint not null,
    stable_anchor varchar(255) not null,
    anchor_type varchar(64) not null,
    target_table varchar(64) not null,
    target_id bigint,
    primary key (id),
    unique key uk_version_stable_anchor (version_id, stable_anchor),
    constraint fk_anchors_version foreign key (version_id) references legal_document_versions(id) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists legal_document_relationships (
    id bigint not null auto_increment,
    document_id bigint not null,
    related_document_id bigint not null,
    relationship_type enum(
        'AMENDS',
        'REPLACES',
        'GUIDES',
        'IMPLEMENTS',
        'REFERENCES',
        'EXPIRES',
        'CONSOLIDATES',
        'CORRECTS',
        'OTHER'
    ) not null,
    source_text varchar(1000),
    primary key (id),
    unique key uk_legal_doc_relationship (document_id, related_document_id, relationship_type),
    index idx_legal_doc_relationship_document (document_id),
    index idx_legal_doc_relationship_related (related_document_id),
    index idx_relationship_type (relationship_type)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists crawl_jobs (
    id bigint not null auto_increment,
    source_url varchar(1500) not null,
    source_url_hash char(64) not null,
    document_id bigint null,
    status varchar(32) not null default 'DISCOVERED',
    attempts int not null default 0,
    last_error text,
    discovered_at timestamp not null default current_timestamp,
    crawled_at timestamp null,
    updated_at timestamp not null default current_timestamp on update current_timestamp,
    primary key (id),
    unique key uk_crawl_jobs_source_url_hash (source_url_hash),
    index idx_crawl_jobs_status (status),
    index idx_crawl_jobs_document_id (document_id)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists pdf_review_documents (
    document_id bigint not null,
    source_url varchar(1500),
    title varchar(1500),
    document_number varchar(255),
    document_type varchar(255),
    issuing_authority varchar(500),
    issued_date date,
    effective_date date,
    expired_date date,
    validity_status varchar(255),
    pdf_file_name varchar(1000),
    extracted_text longtext,
    extracted_html longtext,
    review_reason varchar(255) not null default 'PDF_TEXT_REQUIRES_MANUAL_REVIEW',
    created_at timestamp not null default current_timestamp,
    updated_at timestamp not null default current_timestamp on update current_timestamp,
    primary key (document_id)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;
