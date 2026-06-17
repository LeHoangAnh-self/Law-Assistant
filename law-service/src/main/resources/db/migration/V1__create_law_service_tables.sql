create table legal_documents (
    id bigint not null,
    title varchar(1500) not null,
    document_number varchar(255),
    issued_date date,
    document_type varchar(255),
    effective_date date,
    expired_date date,
    source varchar(500),
    gazette_date_raw varchar(255),
    sector varchar(255),
    field varchar(1000),
    issuing_authority varchar(500),
    signer_title varchar(255),
    signer_name varchar(255),
    scope varchar(500),
    application_info double,
    validity_status varchar(255),
    embedding_status varchar(32) not null default 'PENDING',
    indexed_at timestamp(6) null,
    created_at timestamp(6) not null default current_timestamp(6),
    updated_at timestamp(6) not null default current_timestamp(6) on update current_timestamp(6),
    primary key (id),
    index idx_legal_documents_type (document_type),
    index idx_legal_documents_status (validity_status),
    index idx_legal_documents_issued_date (issued_date),
    fulltext index ft_legal_documents_title_number (title, document_number)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table legal_document_contents (
    document_id bigint not null,
    content_html mediumtext not null,
    content_text mediumtext,
    created_at timestamp(6) not null default current_timestamp(6),
    updated_at timestamp(6) not null default current_timestamp(6) on update current_timestamp(6),
    primary key (document_id),
    fulltext index ft_legal_document_contents_text (content_text)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table legal_document_relationships (
    id bigint not null auto_increment,
    document_id bigint not null,
    related_document_id bigint not null,
    relationship_type varchar(255) not null,
    primary key (id),
    unique key uk_legal_doc_relationship (document_id, related_document_id, relationship_type),
    index idx_legal_doc_relationship_document (document_id),
    index idx_legal_doc_relationship_related (related_document_id)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;
