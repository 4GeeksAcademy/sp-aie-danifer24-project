-- Least-privilege RLS policies for the dedicated ETL writer.
-- Run as a database owner/admin after confirming the role exists.
-- The role may only manage reporting rows and runs; source telemetry is untouched.

GRANT USAGE ON SCHEMA reporting TO nexova_reporting_writer;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON reporting.weekly_office_program_performance
    TO nexova_reporting_writer;
GRANT SELECT, INSERT, UPDATE
    ON reporting.pipeline_runs
    TO nexova_reporting_writer;

-- KPI rows can only be created/updated in allowed office/currency combinations.
CREATE POLICY reporting_writer_kpi_select
    ON reporting.weekly_office_program_performance
    FOR SELECT TO nexova_reporting_writer
    USING (true);
CREATE POLICY reporting_writer_kpi_insert
    ON reporting.weekly_office_program_performance
    FOR INSERT TO nexova_reporting_writer
    WITH CHECK (
        (office = 'valencia' AND currency = 'EUR')
        OR (office = 'miami' AND currency = 'USD')
    );
CREATE POLICY reporting_writer_kpi_update
    ON reporting.weekly_office_program_performance
    FOR UPDATE TO nexova_reporting_writer
    USING (true)
    WITH CHECK (
        (office = 'valencia' AND currency = 'EUR')
        OR (office = 'miami' AND currency = 'USD')
    );
CREATE POLICY reporting_writer_kpi_delete
    ON reporting.weekly_office_program_performance
    FOR DELETE TO nexova_reporting_writer
    USING (true);

-- Audit rows are visible to this writer only for its own ETL flow name.
CREATE POLICY reporting_writer_runs_select
    ON reporting.pipeline_runs
    FOR SELECT TO nexova_reporting_writer
    USING (flow_name = 'weekly_office_program_performance');
CREATE POLICY reporting_writer_runs_insert
    ON reporting.pipeline_runs
    FOR INSERT TO nexova_reporting_writer
    WITH CHECK (flow_name = 'weekly_office_program_performance');
CREATE POLICY reporting_writer_runs_update
    ON reporting.pipeline_runs
    FOR UPDATE TO nexova_reporting_writer
    USING (flow_name = 'weekly_office_program_performance')
    WITH CHECK (flow_name = 'weekly_office_program_performance');
