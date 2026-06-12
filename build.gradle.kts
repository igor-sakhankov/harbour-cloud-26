plugins {
	java
	id("org.springframework.boot") version "4.0.6"
	id("io.spring.dependency-management") version "1.1.7"
}

group = "space.harbour"
version = "0.0.1-SNAPSHOT"

java {
	toolchain {
		languageVersion = JavaLanguageVersion.of(25)
	}
}

repositories {
	mavenCentral()
}

dependencies {
	implementation("org.springframework.boot:spring-boot-starter-webmvc")
	implementation("org.springframework.boot:spring-boot-starter-validation")
	// Exposes /actuator/health on each backend instance, which the load balancer probes.
	implementation("org.springframework.boot:spring-boot-starter-actuator")
	developmentOnly("org.springframework.boot:spring-boot-docker-compose")
	testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
	testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

// Two @SpringBootApplication classes live in this module (the payments app and the
// load balancer), so the default main class for bootRun/bootJar must be pinned.
// The balancer is launched separately via the bootRunLb task.
springBoot {
	mainClass = "space.harbour.cloud.CloudApplication"
}

tasks.withType<Test> {
	useJUnitPlatform()
}

tasks.register<JavaExec>("importCsv") {
    group = "application"
    mainClass.set("space.harbour.cloud.importer.PaymentCsvImporter")
    classpath = sourceSets["main"].runtimeClasspath
    // ./gradlew importCsv --args="samples/payments-sample.csv http://localhost:9091"
}

// Runs the redirect load balancer (a second, standalone Spring Boot app in this
// module) on the `lb` profile. Normal `bootRun` boots only the payments app.
tasks.register<JavaExec>("bootRunLb") {
    group = "application"
    description = "Runs the redirect (HTTP 302) load balancer on port 8090."
    mainClass = "space.harbour.cloud.lb.LoadBalancerApplication"
    classpath = sourceSets["main"].runtimeClasspath
    args("--spring.profiles.active=lb")
}
