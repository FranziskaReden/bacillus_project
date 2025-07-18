import pandas as pd
import numpy as np
import os 
import argparse
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
import seaborn as sns
import matplotlib.pyplot as plt
from tqdm import tqdm
from scipy.cluster.hierarchy import linkage, leaves_list

from utils import read_fasta, read_fasta_object, read_partitions

def exchange_names(columns:list) -> list:

    new_names = []
    taxonomy = pd.read_csv("gtdb/bac120_taxonomy_expanded.tsv", sep='\t')
    for col in columns:
        indeces = taxonomy[taxonomy['accession']==col].index
        if len(indeces) > 0:
            new_names.append(f'{taxonomy.at[indeces[0], 'genus']}:{taxonomy.at[indeces[0], 'species']}')

        else:
            new_names.append(col)

    return new_names

def plot_identity_matrix_masked(target_folder: str, limit = 0.95, rename: bool = False):
    
    print(f'Plot identity matrix...')

    # Load identity matrix
    matrix = pd.read_csv(os.path.join(target_folder, 'identity_matrix.tsv'), sep='\t', index_col=0)
    
    # Ensure the diagonal is 1
    for col in matrix.columns:
        matrix.at[col, col] = 1

    # Perform hierarchical clustering on the columns
    linkage_matrix = linkage(matrix.T, method="average")  # Cluster columns
    column_order = leaves_list(linkage_matrix)  # Get the order of columns

    # Reorder the matrix based on clustering
    clustered_matrix = matrix.iloc[:, column_order].iloc[column_order, :]

    # Apply name renaming if needed
    if rename:
        new_names = exchange_names(clustered_matrix.columns)
    else:
        new_names = clustered_matrix.columns

    # Mask values below limit
    masked_matrix = clustered_matrix.copy()
    masked_matrix[masked_matrix < limit] = np.nan  # Convert values <0.95 to NaN

    # Plot the heatmap
    plt.figure(figsize=(20, 17))
    ax = sns.heatmap(
        masked_matrix,
        annot=False,
        cmap="YlGnBu",
        cbar=True,
        mask=np.isnan(masked_matrix)  # Mask NaN values
    )

    # Force all tick labels to appear
    ax.set_xticks(np.arange(clustered_matrix.shape[1]) + 0.5)
    ax.set_yticks(np.arange(clustered_matrix.shape[0]) + 0.5)
    ax.set_xticklabels(new_names, rotation=90, ha="right", fontsize=2)
    ax.set_yticklabels(new_names, rotation=0, fontsize=2)

    plt.title("Identity matrix of GTDB genomes and assemblies", fontsize=20)

    # Save the plot
    output_file = f'identity_matrix_{limit}_renamed.pdf' if rename else f'identity_matrix_{limit}.pdf'
    plt.savefig(os.path.join(target_folder, output_file), bbox_inches='tight', format='pdf', dpi=200)
    plt.show()

def plot_identity_matrix(target_folder:str, rename:bool = False):

    print(f'Plot identity matrix...')

    matrix = pd.read_csv(os.path.join(target_folder, 'identity_matrix.tsv'), sep='\t', index_col=0)
    for col in matrix.columns:
        matrix.at[col, col] = 1

    # Perform hierarchical clustering on the columns
    linkage_matrix = linkage(matrix.T, method="average")  # Cluster columns
    column_order = leaves_list(linkage_matrix)  # Get the order of columns

    # Reorder the matrix based on clustering
    clustered_matrix = matrix.iloc[:, column_order].iloc[column_order, :]

    if rename is True:
        new_names = exchange_names(clustered_matrix.columns)
    else:
        new_names = clustered_matrix.columns

    # Plot the heatmap
    plt.figure(figsize=(20, 17))
    ax = sns.heatmap(
        clustered_matrix,
        annot=False,
        cmap="YlGnBu",
        cbar=True
    )

    # Force all tick labels to appear
    ax.set_xticks(np.arange(clustered_matrix.shape[1]) + 0.5)
    ax.set_yticks(np.arange(clustered_matrix.shape[0]) + 0.5)
    ax.set_xticklabels(new_names, rotation = 90, ha="right", fontsize=2)
    ax.set_yticklabels(new_names, rotation=0, fontsize=2)

    plt.title("Identity matrix of GTDB genomes and assemblies", fontsize=20)
    if rename is True:
        plt.savefig(os.path.join(target_folder, 'identity_matrix_renamed.pdf'), bbox_inches='tight', format='pdf', dpi=200)
    else:
        plt.savefig(os.path.join(target_folder, 'identity_matrix.pdf'), bbox_inches='tight', format='pdf', dpi=200)
    plt.show()

def calc_identity(seq1:str, seq2:str, partitions:list) -> float:

    overall_length = len(seq1)
    score = 0

    for limit1, limit2 in partitions:
        length = limit2-limit1
        sub_seq1 = seq1[limit1:limit2]
        sub_seq2 = seq2[limit1:limit2]
        if any(seq == '-'*length for seq in [sub_seq1, sub_seq2]):
            overall_length -= length

        else:
            for i in range (length):
                if sub_seq1[i] == sub_seq2[i]:
                    if sub_seq1[i] == '-':
                        overall_length -= 1
                    else:
                        score += 1

    return score/overall_length

def calc_identity_matrix(folder:str, records:dict) -> pd.DataFrame:

    # Define row and column names
    row_names = records.keys()
    column_names = records.keys()

    partitions = read_partitions(os.path.join(folder, 'partitions.txt'))
    #print(partitions)

    # Create an empty DataFrame with the specified row and column names
    matrix = pd.DataFrame(index=row_names, columns=column_names)

    print(f'Calculating pairwise identities between genomes...')

    for name1, seq1 in tqdm(records.items()):
        for name2, seq2 in records.items():
            if name1 != name2:
                if matrix.isnull().loc[name1, name2]:
                    identity = calc_identity(seq1, seq2, partitions)
                    if identity >= 0.99:
                        print(f'Very similar:\t{name1}, {name2}')
                    matrix.at[name1, name2] = identity
                    matrix.at[name2, name1] = identity
            else:
                matrix.at[name1, name2] = 1

    matrix.to_csv(os.path.join(folder, 'identity_matrix.tsv'), sep='\t', index = True)

    return matrix

def retireve_genomes_names(files:list) -> dict:

    list_taxa = {}
    
    for file in files:
        alignment = read_fasta(file)
        
        for name, seq in alignment.items():
            if name not in list_taxa.keys():
                list_taxa[name] = False
    
    return list_taxa

def create_super_alignment(folder:str, target_folder:str) -> dict:

    print(f'Checking gene alignments...')
    files = [os.path.join(folder, file) for file in os.listdir(folder) if file.endswith('.afa')]
    files.sort()
    
    list_taxa = retireve_genomes_names(files) 
    
    print(f'Overall, there are {len(files)} gene alignments with a maximum of {len(list_taxa.keys())} genomes each.')
    print(f'Creating super alignment...')

    super_alignment = {}
    partitions = {}
    current_position = 0
    for file in files:
        for key, item in list_taxa.items():
            list_taxa[key] = False
        
        # Read in alignment file
        alignment = read_fasta(file)

        for name, seq in alignment.items():
            length = len(seq)
            partitions[file] = [current_position, current_position+length]

            if name not in super_alignment.keys():
                super_alignment[name] = ''
            super_alignment[name] += seq
            list_taxa[name] = True

        for key, item in list_taxa.items():
            if key not in super_alignment.keys():
                super_alignment[key] = ''
            if item is False:
                super_alignment[key] += '-'*length

        current_position = partitions[file][1]

    records = [
        SeqRecord(Seq(sequence), id=name, description="") 
        for name, sequence in super_alignment.items()
    ]

    # Write the records to a FASTA file
    if not os.path.exists(target_folder):
        os.mkdir(target_folder)

    target_file = os.path.join(target_folder, 'superalignment.fna')
    with open(target_file, "w") as handle:
        SeqIO.write(records, handle, "fasta")

    with open(os.path.join(target_folder, 'partitions.txt'), 'w') as w:
        for gene, partition in partitions.items():
            w.write(f'DNA, {gene.split('/')[-1].replace('.fna.afa', '')} = {partition[0]+1}-{partition[1]}\n')

    print(f'Super alignment was written into {target_file}.')

    return super_alignment

def remove_close_genomes(target_folder):

    to_be_removed = []
    rename = {}
    assembly_groups = [[221, 244], [662, 656, 658], [218, 215, 224], [398, 342]]
    for a in assembly_groups:
        keep_name = f'SRL{a[0]}_assembly'
        rename[keep_name] = f'SRL{a[0]}'
        for item in a[1:]:
            to_be_removed.append(f'SRL{item}_assembly')
            rename[keep_name] += f'_{item}'
        rename[keep_name] += f'_assembly'
        print(keep_name, rename[keep_name])

    matrix = pd.read_csv(os.path.join(target_folder, 'identity_matrix.tsv'), sep='\t', index_col=0)

    alignment = read_fasta_object(os.path.join(target_folder, 'superalignment.fna'))
    tmp = 0
    for col in matrix.columns:
        for idx in matrix.index.to_list()[tmp:]:
            if col != idx:
                if matrix.at[col, idx] >= 0.99 and not any('assembly' in name for name in [col, idx]):
                    print(f'{idx} {col} : {matrix.at[col, idx]}')
                    string1 = str(alignment[idx])
                    string2 = str(alignment[col])

                    if string1.count('-') >= string2.count('-'):
                        to_be_removed.append(col)
                    else:
                        to_be_removed.append(idx)
        tmp+=1

    filtered_seqeucens = []
    for name, record, in alignment.items():
        if name not in to_be_removed:
            if name in rename.keys():
                record.id = rename[name]
                record.description = ''
            filtered_seqeucens.append(record)

    with open(os.path.join(target_folder, 'superalignment_reduced.fna'), 'w') as handle:
        SeqIO.write(filtered_seqeucens, handle, "fasta")

    alignment = read_fasta_object(os.path.join(target_folder, 'superalignment_reduced.fna'))
    
    partitions = {}
    with open(os.path.join(target_folder, 'partitions.txt')) as f:
        lines = f.readlines()
    for line in lines:
        limit = line.strip().split(' = ')[-1].split('-')
        gene = line.strip().split(' = ')[0].split(', ')[1]
        partitions[gene] = [int(limit[0])-1, int(limit[1])]

    for gene, limits in partitions.items():
        start, end = limits
        # Create an output file for each gene
        with open(os.path.join(target_folder, f'{gene}.fna'), 'w') as w:
            for gene, record in alignment.items():
                # Slice the sequence according to the partition's limits
                sliced_seq = record.seq[start:end]
                if not sliced_seq == '-'*len(sliced_seq):
                    # Write the header and the sliced sequence to the file
                    w.write(f">{record.id}\n{sliced_seq}\n")

def main():

    parser = argparse.ArgumentParser(description="Create super alignments from the marker genes.")
    parser.add_argument("--folder", "-f", type=str, help="Name of the folder containing aignments.")
    args = parser.parse_args()

    target_folder = 'alignments/supermatrix'
    #super_alignment = create_super_alignment(args.folder, target_folder)
    #matrix = calc_identity_matrix(target_folder, super_alignment)
    #plot_identity_matrix(target_folder)
    #plot_identity_matrix(target_folder, rename=True)

    #plot_identity_matrix_masked(target_folder, limit=0.99)
    #plot_identity_matrix_masked(target_folder, limit=0.99, rename=True)

    remove_close_genomes(target_folder)
    return 0

if __name__ == "__main__":
    main()