pipeline {
    agent any

    parameters {
        booleanParam(
            name: 'TRACE_INGESTION_SMOKE_TEST',
            defaultValue: false,
            description: 'Emit a controlled failure signature to verify end-to-end TRACE ingestion.'
        )
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
            steps {
                dir('frontend') {
                    bat 'npm ci'
                    bat 'npm run build'
                }
            }
        }

        stage('TRACE ingestion smoke fixture') {
            when {
                expression { params.TRACE_INGESTION_SMOKE_TEST }
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
                env.TRACE_BUILD_RESULT = currentBuild.currentResult ?: 'UNKNOWN'
                int uploadStatus = bat(
                    returnStatus: true,
                    script: 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\\jenkins_post_build.ps1'
                )
                if (uploadStatus != 0) {
                    echo 'TRACE log delivery failed; this does not change the Jenkins build result.'
                }
            }
        }
    }
}
