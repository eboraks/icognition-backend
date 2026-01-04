//
//  EntityTreeFilterView.swift
//  iso-app
//
//  Created by AI Assistant on 12/6/25.
//

import SwiftUI
import TreePicker

// MARK: - Entity Tree Filter View

struct EntityTreeFilterView: View {
    @Binding var selectedEntityIds: Set<Int>
    @Binding var isPresented: Bool
    
    @State private var entityTree: EntityTreeResponse?
    @State private var isLoading = true
    @State private var searchText = ""
    @State private var treePickerSelection: Set<String> = []
    
    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                
                TextField("Search Topics", text: $searchText)
                    .textFieldStyle(PlainTextFieldStyle())
                
                if !searchText.isEmpty {
                    Button("Clear") {
                        searchText = ""
                    }
                    .foregroundColor(.secondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(.systemGray6))
            .cornerRadius(10)
            .padding()
            
            // Tree view
            if isLoading {
                VStack(spacing: 16) {
                    ProgressView()
                    Text("Loading filters...")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let tree = entityTree {
                let filteredTree = filteredNodes(tree.tree)
                
                // Use OutlineGroup directly for tree display with checkboxes
                List {
                    OutlineGroup(filteredTree, id: \.key, children: \.children) { node in
                        EntityTreeRowView(
                            node: node,
                            selectedKeys: $treePickerSelection
                        )
                    }
                }
                .listStyle(PlainListStyle())
                .onChange(of: treePickerSelection) { newSelection in
                    // Map TreePicker selections (node keys) back to entity IDs
                    // Only include leaf nodes (nodes with data) in the selection
                    var entityIds: Set<Int> = []
                    func collectEntityIds(from nodes: [EntityTreeNode]) {
                        for node in nodes {
                            // Only process leaf nodes (nodes with data/entityId)
                            if let data = node.data, newSelection.contains(node.key) {
                                entityIds.insert(data.entityId)
                            }
                            // Recursively check children
                            if let children = node.children {
                                collectEntityIds(from: children)
                            }
                        }
                    }
                    collectEntityIds(from: filteredTree)
                    selectedEntityIds = entityIds
                    
                    // Remove any non-leaf node selections from treePickerSelection
                    // This ensures only leaf nodes remain selected
                    var validSelections: Set<String> = []
                    func collectValidSelections(from nodes: [EntityTreeNode]) {
                        for node in nodes {
                            if let data = node.data, newSelection.contains(node.key) {
                                validSelections.insert(node.key)
                            }
                            if let children = node.children {
                                collectValidSelections(from: children)
                            }
                        }
                    }
                    collectValidSelections(from: filteredTree)
                    if validSelections != treePickerSelection {
                        treePickerSelection = validSelections
                    }
                }
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    
                    Text("Failed to load filters")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    
                    Button("Retry") {
                        Task {
                            await loadEntityTree()
                        }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            
            // Selected count footer
            if !selectedEntityIds.isEmpty {
                HStack {
                    Text("\(selectedEntityIds.count) Selected Filters")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Spacer()
                    
                    Button("Clear") {
                        selectedEntityIds.removeAll()
                        treePickerSelection.removeAll()
                    }
                    .font(.caption)
                    .foregroundColor(.blue)
                }
                .padding()
                .background(Color(.systemGray6))
            }
        }
        .navigationTitle("Filters")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button("Done") {
                    isPresented = false
                }
            }
        }
        .task {
            await loadEntityTree()
        }
        .onAppear {
            // Sync initial selection state from entity IDs to node keys
            syncSelectionToTreePicker()
        }
    }
    
    private func loadEntityTree() async {
        isLoading = true
        AppLogger.ui("EntityTreeFilterView: Fetching entity tree", level: .info)
        
        if let treeResponse = await EntityTreeAPIService.shared.fetchEntityTree() {
            await MainActor.run {
                self.entityTree = treeResponse
                self.isLoading = false
                // Sync selection state after loading
                self.syncSelectionToTreePicker()
                AppLogger.ui("EntityTreeFilterView: Loaded entity tree with \(treeResponse.tree.count) root nodes", level: .info)
            }
        } else {
            await MainActor.run {
                self.isLoading = false
                AppLogger.ui("EntityTreeFilterView: Failed to load entity tree", level: .error)
            }
        }
    }
    
    private func filteredNodes(_ nodes: [EntityTreeNode]) -> [EntityTreeNode] {
        if searchText.isEmpty {
            return nodes
        }
        
        return nodes.compactMap { node in
            filterNode(node)
        }
    }
    
    private func filterNode(_ node: EntityTreeNode) -> EntityTreeNode? {
        let matchesSearch = node.label.localizedCaseInsensitiveContains(searchText)
        let filteredChildren = node.children?.compactMap { filterNode($0) } ?? []
        
        if matchesSearch || !filteredChildren.isEmpty {
            // Return node with filtered children
            return EntityTreeNode(
                key: node.key,
                label: node.label,
                children: filteredChildren.isEmpty ? node.children : filteredChildren,
                data: node.data
            )
        }
        return nil
    }
    
    // Helper to sync selectedEntityIds to treePickerSelection (node keys)
    private func syncSelectionToTreePicker() {
        guard let tree = entityTree else { return }
        var nodeKeys: Set<String> = []
        
        func findNodeKeys(from nodes: [EntityTreeNode]) {
            for node in nodes {
                if let data = node.data, selectedEntityIds.contains(data.entityId) {
                    nodeKeys.insert(node.key)
                }
                if let children = node.children {
                    findNodeKeys(from: children)
                }
            }
        }
        
        findNodeKeys(from: tree.tree)
        treePickerSelection = nodeKeys
    }
    
    // Helper to check if a node is a leaf (has data/entityId)
    private func isLeafNode(_ node: EntityTreeNode) -> Bool {
        return node.data != nil
    }
}

// MARK: - Entity Tree Row View

struct EntityTreeRowView: View {
    let node: EntityTreeNode
    @Binding var selectedKeys: Set<String>
    
    var isSelected: Bool {
        selectedKeys.contains(node.key)
    }
    
    var isLeaf: Bool {
        node.data != nil
    }
    
    var body: some View {
        HStack {
            // Checkbox - only show for leaf nodes
            if isLeaf {
                Button(action: {
                    if isSelected {
                        selectedKeys.remove(node.key)
                    } else {
                        selectedKeys.insert(node.key)
                    }
                }) {
                    Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                        .foregroundColor(isSelected ? .blue : .secondary)
                }
                .buttonStyle(.plain)
            } else {
                // Spacer for non-leaf nodes to align text
                Image(systemName: "square")
                    .foregroundColor(.clear)
            }
            
            // Node label
            Text(node.label)
                .font(.body)
                .foregroundColor(.primary)
            
            Spacer()
        }
        .contentShape(Rectangle())
    }
}

