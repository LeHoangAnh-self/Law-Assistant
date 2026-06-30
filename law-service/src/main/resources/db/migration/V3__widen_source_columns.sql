alter table legal_documents
    modify column source varchar(2048) null,
    modify column source_url varchar(2048) null;
