pipeline {
    agent any

    parameters {
        booleanParam(
            name: 'TRACE_INGESTION_SMOKE_TEST',
            defaultValue: false,
            description: 'Emit a controlled failure signature to verify end-to-end TRACE ingestion.'
        )
        string(name: 'TRACE_FINALIZE_BUILD_URL', defaultValue: '', description: 'Internal: completed build whose final console should be ingested.')
        string(name: 'TRACE_SOURCE_JOB_NAME', defaultValue: '', description: 'Internal final-console metadata.')
        string(name: 'TRACE_SOURCE_BUILD_NUMBER', defaultValue: '', description: 'Internal final-console metadata.')
        string(name: 'TRACE_SOURCE_BUILD_RESULT', defaultValue: '', description: 'Internal final-console metadata.')
        string(name: 'TRACE_SOURCE_REPO_URL', defaultValue: '', description: 'Internal final-console metadata.')
        string(name: 'TRACE_SOURCE_COMMIT', defaultValue: '', description: 'Internal final-console metadata.')
        string(name: 'TRACE_SOURCE_BRANCH', defaultValue: '', description: 'Internal final-console metadata.')
    }

    options {
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build dashboard') {
            when {
                expression { !params.TRACE_FINALIZE_BUILD_URL?.trim() }
            }
            steps {
                dir('frontend') {
                    bat 'npm ci'
                    bat 'npm run build'
                }
            }
        }

        stage('TRACE ingestion smoke fixture') {
            when {
                expression { params.TRACE_INGESTION_SMOKE_TEST && !params.TRACE_FINALIZE_BUILD_URL?.trim() }
            }
            steps {
                echo '[ERROR] TRACE_INGESTION_SMOKE: synthetic payment dependency failure; Connection refused to payment-db.test:5432'
                echo 'Caused by: java.net.ConnectException: Connection refused'
            }
        }
    }

    post {
        always {
            script {
                if (params.TRACE_FINALIZE_BUILD_URL?.trim()) {
                    bat "powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\\jenkins_finalize_build.ps1 -BuildUrl \"${params.TRACE_FINALIZE_BUILD_URL}\" -JobName \"${params.TRACE_SOURCE_JOB_NAME}\" -BuildNumber \"${params.TRACE_SOURCE_BUILD_NUMBER}\" -BuildResult \"${params.TRACE_SOURCE_BUILD_RESULT}\" -RepoUrl \"${params.TRACE_SOURCE_REPO_URL}\" -CommitSha \"${params.TRACE_SOURCE_COMMIT}\" -GitBranch \"${params.TRACE_SOURCE_BRANCH}\""
                } else {
                    build job: env.JOB_NAME,
                        parameters: [
                            booleanParam(name: 'TRACE_INGESTION_SMOKE_TEST', value: false),
                            string(name: 'TRACE_FINALIZE_BUILD_URL', value: env.BUILD_URL),
                            string(name: 'TRACE_SOURCE_JOB_NAME', value: env.JOB_NAME ?: ''),
                            string(name: 'TRACE_SOURCE_BUILD_NUMBER', value: env.BUILD_NUMBER ?: ''),
                            string(name: 'TRACE_SOURCE_BUILD_RESULT', value: currentBuild.currentResult ?: 'UNKNOWN'),
                            string(name: 'TRACE_SOURCE_REPO_URL', value: env.GIT_URL ?: ''),
                            string(name: 'TRACE_SOURCE_COMMIT', value: env.GIT_COMMIT ?: ''),
                            string(name: 'TRACE_SOURCE_BRANCH', value: env.BRANCH_NAME ?: env.GIT_BRANCH ?: '')
                        ],
                        wait: false,
                        propagate: false
                    echo 'TRACE scheduled a final-console capture after this build completes.'
                }
            }
        }
    }
}
