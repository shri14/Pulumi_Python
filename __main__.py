import pulumi
from pulumi_aws import eks, ec2, iam, kms, cloudwatch, get_availability_zones
import json

# Get available AZs
available_azs = get_availability_zones(state="available")

# VPC Configuration
vpc = ec2.Vpc("eks-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={
        "Name": "eks-cluster-vpc",
        "kubernetes.io/cluster/my-eks-cluster": "shared"
    })

vpc.id.apply(lambda id: print(f"VPC 'eks-cluster-vpc' created with ID: {id}"))

private_subnet_1 = ec2.Subnet("eks-private-subnet-1",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone=available_azs.names[0],
    map_public_ip_on_launch=False,
    tags={
        "Name": "eks-private-subnet-1",
        "kubernetes.io/cluster/my-eks-cluster": "shared",
        "kubernetes.io/role/internal-elb": "1"
    })

private_subnet_2 = ec2.Subnet("eks-private-subnet-2",
    vpc_id=vpc.id,
    cidr_block="10.0.2.0/24",
    availability_zone=available_azs.names[1],
    map_public_ip_on_launch=False,
    tags={
        "Name": "eks-private-subnet-2",
        "kubernetes.io/cluster/my-eks-cluster": "shared",
        "kubernetes.io/role/internal-elb": "1"
    })

public_subnet_1 = ec2.Subnet("eks-public-subnet-1",
    vpc_id=vpc.id,
    cidr_block="10.0.3.0/24",
    availability_zone=available_azs.names[0],
    map_public_ip_on_launch=True,
    tags={
        "Name": "eks-public-subnet-1",
        "kubernetes.io/cluster/my-eks-cluster": "shared",
        "kubernetes.io/role/elb": "1"
    })

public_subnet_2 = ec2.Subnet("eks-public-subnet-2",
    vpc_id=vpc.id,
    cidr_block="10.0.4.0/24",
    availability_zone=available_azs.names[1],
    map_public_ip_on_launch=True,
    tags={
        "Name": "eks-public-subnet-2",
        "kubernetes.io/cluster/my-eks-cluster": "shared",
        "kubernetes.io/role/elb": "1"
    })

igw = ec2.InternetGateway("eks-igw", 
    vpc_id=vpc.id,
    tags={"Name": "eks-internet-gateway"})

nat_eip = ec2.Eip("eks-nat-eip", 
    domain="vpc",
    tags={"Name": "eks-nat-gateway-eip"})

nat_gateway = ec2.NatGateway("eks-nat-gateway",
    allocation_id=nat_eip.id,
    subnet_id=public_subnet_1.id,
    tags={"Name": "eks-nat-gateway"})

# Route Tables
public_route_table = ec2.RouteTable("eks-public-rt",
    vpc_id=vpc.id,
    routes=[ec2.RouteTableRouteArgs(
        cidr_block="0.0.0.0/0",
        gateway_id=igw.id
    )],
    tags={"Name": "eks-public-rt"})

ec2.RouteTableAssociation("eks-public-rta-1",
    route_table_id=public_route_table.id,
    subnet_id=public_subnet_1.id)

ec2.RouteTableAssociation("eks-public-rta-2",
    route_table_id=public_route_table.id,
    subnet_id=public_subnet_2.id)

private_route_table = ec2.RouteTable("eks-private-rt",
    vpc_id=vpc.id,
    routes=[ec2.RouteTableRouteArgs(
        cidr_block="0.0.0.0/0",
        nat_gateway_id=nat_gateway.id
    )],
    tags={"Name": "eks-private-rt"})

ec2.RouteTableAssociation("eks-private-rta-1",
    route_table_id=private_route_table.id,
    subnet_id=private_subnet_1.id)

ec2.RouteTableAssociation("eks-private-rta-2",
    route_table_id=private_route_table.id,
    subnet_id=private_subnet_2.id)

# IAM Roles
eks_role = iam.Role("eks-cluster-role",
    name="eks-cluster-role",
    assume_role_policy=iam.get_policy_document(statements=[{
        "actions": ["sts:AssumeRole"],
        "principals": [{
            "type": "Service",
            "identifiers": ["eks.amazonaws.com"],
        }],
    }]).json)

node_role = iam.Role("eks-node-role",
    name="eks-node-role",
    assume_role_policy=iam.get_policy_document(statements=[{
        "actions": ["sts:AssumeRole"],
        "principals": [{
            "type": "Service",
            "identifiers": ["ec2.amazonaws.com"],
        }],
    }]).json)

# Attach necessary policies to roles
iam.RolePolicyAttachment("eks-cluster-policy-attachment",
    policy_arn="arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
    role=eks_role.name)

iam.RolePolicyAttachment("eks-node-policy-attachment-1",
    policy_arn="arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    role=node_role.name)

iam.RolePolicyAttachment("eks-node-policy-attachment-2",
    policy_arn="arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    role=node_role.name)

iam.RolePolicyAttachment("eks-node-policy-attachment-3",
    policy_arn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    role=node_role.name)

# Security Groups
cluster_sg = ec2.SecurityGroup("eks-cluster-sg",
    name="eks-cluster-sg",
    vpc_id=vpc.id,
    description="EKS cluster security group")

node_sg = ec2.SecurityGroup("eks-node-sg",
    name="eks-node-sg",
    vpc_id=vpc.id,
    description="EKS node security group")

# KMS Key for future use
kms_key = kms.Key("eks-kms-key",
    description="KMS key for EKS (currently unused)",
    enable_key_rotation=True,
    tags={"Name": "eks-secrets-kms-key"})

# EKS Cluster
cluster = eks.Cluster("eks-cluster",
    name="my-eks-cluster",
    role_arn=eks_role.arn,
    version="1.30",
    vpc_config=eks.ClusterVpcConfigArgs(
        subnet_ids=[private_subnet_1.id, private_subnet_2.id, public_subnet_1.id, public_subnet_2.id],
        endpoint_private_access=True,
        endpoint_public_access=True,  # Changed to True for troubleshooting
    ))

print("EKS Cluster 'my-eks-cluster' created")

cluster.vpc_config.apply(lambda vpc_config: 
    print(f"Cluster endpoint private access: {vpc_config.endpoint_private_access}"))
cluster.vpc_config.apply(lambda vpc_config: 
    print(f"Cluster endpoint public access: {vpc_config.endpoint_public_access}"))

# Node Groups
staging_node_group = eks.NodeGroup("eks-staging-node-group",
    cluster_name=cluster.name,
    node_group_name="staging-node-group",
    node_role_arn=node_role.arn,
    subnet_ids=[private_subnet_1.id, private_subnet_2.id],
    scaling_config={
        "desired_size": 1,
        "max_size": 1,
        "min_size": 1,
    },
    instance_types=["t3.small"],
    tags={"Environment": "Staging"})

print("Staging Node Group 'staging-node-group' created")
staging_node_group.scaling_config.apply(lambda config: 
    print(f"Staging Node Group desired size: {config['desired_size']}"))

production_node_group = eks.NodeGroup("eks-production-node-group",
    cluster_name=cluster.name,
    node_group_name="production-node-group",
    node_role_arn=node_role.arn,
    subnet_ids=[private_subnet_1.id, private_subnet_2.id],
    scaling_config={
        "desired_size": 1,
        "max_size": 1,
        "min_size": 1,
    },
    instance_types=["t3.small"],
    tags={"Environment": "Production"})

print("Production Node Group 'production-node-group' created")
production_node_group.scaling_config.apply(lambda config: 
    print(f"Production Node Group desired size: {config['desired_size']}"))

# CloudWatch Log Group
log_group = cloudwatch.LogGroup("eks-log-group",
    name="/aws/eks/my-eks-cluster/cluster",
    retention_in_days=7)

print(f"CloudWatch Log Group '/aws/eks/my-eks-cluster/cluster' created")

# Generate kubeconfig
def generate_kubeconfig(cluster_name, cluster_endpoint, cluster_ca):
    return json.dumps({
        "apiVersion": "v1",
        "clusters": [{
            "cluster": {
                "server": cluster_endpoint,
                "certificate-authority-data": cluster_ca,
            },
            "name": "kubernetes",
        }],
        "contexts": [{
            "context": {
                "cluster": "kubernetes",
                "user": "aws",
            },
            "name": "aws",
        }],
        "current-context": "aws",
        "kind": "Config",
        "users": [{
            "name": "aws",
            "user": {
                "exec": {
                    "apiVersion": "client.authentication.k8s.io/v1beta1",
                    "command": "aws",
                    "args": [
                        "eks",
                        "get-token",
                        "--cluster-name",
                        cluster_name,
                    ],
                },
            },
        }],
    })

# Export cluster name and kubeconfig
pulumi.export("cluster_name", cluster.name)
pulumi.export("kubeconfig", pulumi.Output.all(cluster.name, cluster.endpoint, cluster.certificate_authority.data) \
              .apply(lambda args: generate_kubeconfig(args[0], args[1], args[2])))

print("Pulumi stack creation completed.")