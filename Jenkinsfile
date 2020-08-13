def GET_TIME() {
    def NOW = new Date()
    TIME = NOW.format("yyyyMMddHHmmss")
    return TIME
}

pipeline{
    environment {
        TIMESTAMP = GET_TIME()
    }
    stages {
        stage('Stage 1') {
            steps {
                sh "sleep 60"
            }
        }
        stage('Stage 2') {
            steps {
                sh "sleep 30"
            }
        }
    }
}