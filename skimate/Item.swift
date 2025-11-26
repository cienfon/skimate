//
//  Item.swift
//  skimate
//
//  Created by Jeff Tang on 2025/11/26.
//

import Foundation
import SwiftData

@Model
final class Item {
    var timestamp: Date
    
    init(timestamp: Date) {
        self.timestamp = timestamp
    }
}
