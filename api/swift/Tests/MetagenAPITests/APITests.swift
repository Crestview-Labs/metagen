// Basic API client tests
import XCTest
@testable import MetagenAPI

final class APITests: XCTestCase {
    func testAPICreation() {
        let api = MetagenAPI()
        XCTAssertNotNil(api)
    }
    
    func testAPICreationWithCustomURL() {
        let api = MetagenAPI(baseURL: "http://localhost:3000")
        XCTAssertNotNil(api)
    }
    
    func testVersionConstants() {
        XCTAssertEqual(APIVersion.version, "0.1.0")
        XCTAssertEqual(APIVersion.build, "2025.01.08.001")
        XCTAssertEqual(APIVersion.releaseDate, "2025-01-08")
    }
}